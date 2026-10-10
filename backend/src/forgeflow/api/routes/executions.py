from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import func, select
from sse_starlette.sse import EventSourceResponse

from forgeflow.api.deps import ContainerDep, Operator, PageDep, Viewer
from forgeflow.api.errors import APIError
from forgeflow.api.schemas import (
    AgentRunOut,
    EventOut,
    ExecutionCreate,
    ExecutionDetail,
    ExecutionOut,
    Page,
    ToolCallOut,
    TraceOut,
)
from forgeflow.db.models import AgentRun, Approval, Execution, ExecutionEvent, Repository, ToolCall
from forgeflow.operations import OperationError, cancel_execution, create_execution, retry_execution
from forgeflow.schemas import TERMINAL_STATUSES

log = logging.getLogger("forgeflow.api")

router = APIRouter(prefix="/api/executions", tags=["executions"])


def _out(ex: Execution, repo_name: str | None) -> dict[str, Any]:
    duration = None
    if ex.started_at and ex.finished_at:
        duration = int((ex.finished_at - ex.started_at).total_seconds() * 1000)
    data = {k: getattr(ex, k) for k in ExecutionOut.model_fields if hasattr(ex, k)}
    data.update(repository_name=repo_name, duration_ms=duration)
    return data


def _op(exc: OperationError) -> APIError:
    return APIError(exc.status, exc.code, exc.message)


@router.post("", response_model=ExecutionOut, status_code=201, summary="Submit an engineering request")
async def create(body: ExecutionCreate, c: ContainerDep, p: Operator) -> dict[str, Any]:
    try:
        ex = await create_execution(
            c,
            repository_id=body.repository_id,
            workflow=body.workflow,
            request=body.request,
            params=dict(body.params),
            actor=p.actor,
        )
    except OperationError as exc:
        raise _op(exc) from exc
    async with c.services.db.session() as s:
        repo = await s.get(Repository, ex.repository_id)
    return _out(ex, repo.full_name if repo else None)


@router.get("", response_model=Page[ExecutionOut], summary="List executions")
async def list_executions(
    c: ContainerDep,
    _: Viewer,
    page: PageDep,
    status: Annotated[str | None, Query()] = None,
    repository_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    q = select(Execution, Repository.full_name).join(Repository, Repository.id == Execution.repository_id)
    cq = select(func.count(Execution.id))
    if status:
        statuses = status.split(",")
        q, cq = q.where(Execution.status.in_(statuses)), cq.where(Execution.status.in_(statuses))
    if repository_id:
        q, cq = q.where(Execution.repository_id == repository_id), cq.where(Execution.repository_id == repository_id)
    async with c.services.db.session() as s:
        total = await s.scalar(cq) or 0
        rows = (await s.execute(q.order_by(Execution.created_at.desc()).limit(page.limit).offset(page.offset))).all()
    return {"items": [_out(ex, name) for ex, name in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{execution_id}", response_model=ExecutionDetail, summary="Execution detail with report and state")
async def get(execution_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    async with c.services.db.session() as s:
        ex = await s.get(Execution, execution_id)
        if ex is None:
            raise APIError(404, "not_found", "Execution not found")
        repo = await s.get(Repository, ex.repository_id)
        pending = await s.scalar(
            select(Approval.id).where(Approval.execution_id == ex.id, Approval.status == "pending")
        )
    data = _out(ex, repo.full_name if repo else None)
    data["report"] = ex.report
    data["pending_approval_id"] = pending
    data["simulated"] = c.services.llm.simulated
    if ex.report is None:
        # Live view of checkpointed state for in-flight executions (large fields trimmed).
        snap = await c.engine.snapshot(ex.id, ex.workflow)
        values = snap["values"]
        data["state"] = {
            "next": snap["next"],
            **{
                k: values.get(k)
                for k in (
                    "plan",
                    "batches",
                    "batch_index",
                    "applied",
                    "test_run",
                    "debug_attempts",
                    "diagnoses",
                    "review",
                    "verification",
                    "pr_draft",
                    "changed",
                    "summary",
                    "reproduction",
                )
            },
            "diff": (values.get("diff") or "")[:400_000],
        }
    return data


@router.post("/{execution_id}/cancel", response_model=ExecutionOut, summary="Cancel an execution")
async def cancel(execution_id: str, c: ContainerDep, p: Operator) -> dict[str, Any]:
    try:
        ex = await cancel_execution(c, execution_id, p.actor)
    except OperationError as exc:
        raise _op(exc) from exc
    return _out(ex, None)


@router.post(
    "/{execution_id}/retry", response_model=ExecutionOut, summary="Resume a failed execution from its last checkpoint"
)
async def retry(execution_id: str, c: ContainerDep, p: Operator) -> dict[str, Any]:
    try:
        ex = await retry_execution(c, execution_id, p.actor)
    except OperationError as exc:
        raise _op(exc) from exc
    return _out(ex, None)


@router.get("/{execution_id}/events/history", response_model=list[EventOut], summary="Stored events (JSON)")
async def event_history(
    execution_id: str, c: ContainerDep, _: Viewer, after: Annotated[int, Query(ge=0)] = 0
) -> list[ExecutionEvent]:
    return await c.services.events.since(execution_id, after, limit=2000)


@router.get(
    "/{execution_id}/events",
    summary="Live event stream (Server-Sent Events)",
    description="Resumable with the Last-Event-ID header or ?after=<seq>. Each event id is the sequence number.",
)
async def events(
    execution_id: str,
    request: Request,
    c: ContainerDep,
    _: Viewer,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    async with c.services.db.session() as s:
        if await s.get(Execution, execution_id) is None:
            raise APIError(404, "not_found", "Execution not found")
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
    bus = c.services.events

    async def stream() -> AsyncIterator[dict[str, Any]]:
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            batch = await bus.since(execution_id, cursor)
            for ev in batch:
                cursor = ev.seq
                yield {"id": str(ev.seq), "event": ev.type, "data": EventOut.model_validate(ev).model_dump_json()}
            if batch:
                idle = 0
                continue
            async with c.services.db.session() as s:
                ex = await s.get(Execution, execution_id)
                status = ex.status if ex else "failed"
            if status in TERMINAL_STATUSES:
                idle += 1
                if idle > 1:  # one extra pass to flush late events, then close
                    yield {"event": "stream.end", "data": json.dumps({"status": status})}
                    return
            await bus.wait(execution_id, timeout=1.0)

    return EventSourceResponse(stream(), ping=15)


@router.get("/{execution_id}/trace", response_model=TraceOut, summary="Agent runs and tool calls")
async def trace(execution_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    async with c.services.db.session() as s:
        runs = list(
            await s.scalars(select(AgentRun).where(AgentRun.execution_id == execution_id).order_by(AgentRun.started_at))
        )
        tools = list(
            await s.scalars(select(ToolCall).where(ToolCall.execution_id == execution_id).order_by(ToolCall.started_at))
        )
    totals = {
        "runs": len(runs),
        "tool_calls": len(tools),
        "input_tokens": sum(r.input_tokens for r in runs),
        "output_tokens": sum(r.output_tokens for r in runs),
        "cost_usd": round(sum(r.cost_usd for r in runs), 6),
        "llm_calls": sum(r.llm_calls for r in runs),
        "failed_runs": sum(1 for r in runs if r.status == "failed"),
        "retries": sum(1 for r in runs if r.attempt > 1),
        "tool_errors": sum(1 for t in tools if t.status == "failed"),
    }
    return {
        "execution_id": execution_id,
        "runs": [AgentRunOut.model_validate(r) for r in runs],
        "tool_calls": [ToolCallOut.model_validate(t) for t in tools],
        "totals": totals,
    }


@router.get("/{execution_id}/diff", summary="Unified diff of the change (text)")
async def diff(execution_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    async with c.services.db.session() as s:
        ex = await s.get(Execution, execution_id)
    if ex is None:
        raise APIError(404, "not_found", "Execution not found")
    if ex.report:
        return {"diff": ex.report.get("diff", ""), "changed": ex.report.get("changed", [])}
    values = (await c.engine.snapshot(ex.id, ex.workflow))["values"]
    if values.get("workspace_id") and ex.workflow != "code_review":
        try:
            ws = c.services.workspaces.get(values["workspace_id"], values["branch"])
            return {
                "diff": await c.services.workspaces.diff(ws),
                "changed": await c.services.workspaces.changed_files(ws),
            }
        except Exception:  # workspace may have been cleaned up; fall back to checkpointed diff
            log.debug("live diff unavailable for %s", execution_id, exc_info=True)
    return {"diff": values.get("diff", ""), "changed": values.get("changed", [])}
