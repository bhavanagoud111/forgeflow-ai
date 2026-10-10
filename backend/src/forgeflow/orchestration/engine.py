"""Execution engine: runs workflow graphs with persistent checkpoints.

* Each execution is a LangGraph thread (``thread_id`` = execution id) checkpointed to
  SQLite or Postgres, so a run can pause for approval in one process and resume in another.
* Executions are claimed from the database by workers; the API never runs graphs inline.
* Cancellation sets a flag that every node checks and also cancels the local task.
* Whole-execution and per-node timeouts are enforced with ``asyncio.timeout``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import uuid
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy import func, select, update

from forgeflow.agents.base import Services
from forgeflow.db.models import Execution, ExecutionEvent, Repository, utcnow
from forgeflow.orchestration.runtime import Ctx, ExecutionCancelled
from forgeflow.orchestration.workflows import BUILDERS
from forgeflow.schemas import TERMINAL_STATUSES
from forgeflow.security.redaction import redact

log = logging.getLogger("forgeflow.engine")


async def open_checkpointer(url: str, stack: AsyncExitStack) -> BaseCheckpointSaver[Any]:
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(url))
        await saver.setup()
        return saver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path = url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else url
    return await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(path))


class ExecutionEngine:
    def __init__(self, svc: Services, checkpointer: BaseCheckpointSaver[Any]) -> None:
        self.svc = svc
        self.checkpointer = checkpointer
        self.graphs: dict[str, CompiledStateGraph[Any, Any, Any, Any]] = {
            w.value: build().compile(checkpointer=checkpointer) for w, build in BUILDERS.items()
        }
        self.ctx = Ctx(svc=svc)
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def _config(self, execution_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": execution_id}, "recursion_limit": 200}

    async def initial_state(self, execution: Execution) -> dict[str, Any]:
        async with self.svc.db.session() as s:
            repo = await s.get(Repository, execution.repository_id)
            assert repo is not None
        params = dict(execution.params or {})
        params.setdefault("max_debug_attempts", self.svc.settings.max_debug_attempts)
        return {
            "execution_id": execution.id,
            "workflow": execution.workflow,
            "repository_id": repo.id,
            "repo_name": repo.full_name,
            "repo_provider": repo.provider,
            "request": execution.request,
            "params": params,
            "proposals": [],
        }

    def _check_policy(self) -> None:
        s = self.svc.settings
        if s.sandbox_mode == "local" and not self.svc.llm.simulated and not s.allow_unsafe_local_sandbox:
            raise RuntimeError(
                "Refusing to run model-generated code in the local sandbox. Use FORGEFLOW_SANDBOX_MODE=docker "
                "or runner, or set FORGEFLOW_ALLOW_UNSAFE_LOCAL_SANDBOX=true for trusted development only."
            )

    async def run(self, execution_id: str) -> None:
        """Start, resume or retry an execution depending on its stored status."""
        async with self.svc.db.session() as s:
            ex = await s.get(Execution, execution_id)
            if ex is None:
                return
            status, payload = ex.status, ex.resume_payload
        graph = self.graphs[ex.workflow]
        if status == "queued":
            await self._drive(execution_id, graph, await self.initial_state(ex), "workflow.started")
        elif status == "resuming" and payload and payload.get("retry"):
            await self._drive(execution_id, graph, None, "workflow.resumed")
        elif status == "resuming" and payload:
            await self._drive(execution_id, graph, Command(resume=payload), "workflow.resumed")

    async def _drive(
        self, execution_id: str, graph: CompiledStateGraph[Any, Any, Any, Any], graph_input: Any, start_event: str
    ) -> None:
        svc = self.svc
        async with svc.db.session() as s:
            await s.execute(
                update(Execution)
                .where(Execution.id == execution_id)
                .values(
                    status="running",
                    started_at=func.coalesce(Execution.started_at, utcnow()),
                    resume_payload=None,
                    error=None,
                )
            )
        await svc.events.emit(
            execution_id,
            start_event,
            "Execution started" if start_event == "workflow.started" else "Execution resumed",
            agent_id="orchestrator",
        )
        status, summary, error, report = "failed", None, None, None
        try:
            self._check_policy()
            async with asyncio.timeout(svc.settings.execution_timeout_seconds):
                result = await graph.ainvoke(graph_input, self._config(execution_id), context=self.ctx)
            if result.get("__interrupt__"):
                status = "awaiting_approval"
                summary = "Waiting for human approval."
            else:
                status = {"succeeded": "succeeded", "blocked": "blocked", "rejected": "rejected"}.get(
                    result.get("outcome", ""), "failed"
                )
                summary = result.get("outcome_reason")
                report = result.get("report")
        except (ExecutionCancelled, asyncio.CancelledError):
            status, summary = "cancelled", "Cancelled by user."
        except TimeoutError:
            error = f"Execution exceeded {svc.settings.execution_timeout_seconds}s timeout."
        except Exception as exc:  # recorded and surfaced; checkpoint allows retry
            log.exception("execution %s failed", execution_id)
            error = redact(f"{type(exc).__name__}: {exc}")[:4000]
        async with svc.db.session() as s:
            values: dict[str, Any] = {"status": status, "summary": summary or error, "error": error, "claimed_by": None}
            if report is not None:
                values["report"] = report
            if status in TERMINAL_STATUSES:
                values["finished_at"] = utcnow()
                values["current_node"] = None
            await s.execute(update(Execution).where(Execution.id == execution_id).values(**values))
        if status == "succeeded":
            await svc.events.emit(
                execution_id,
                "workflow.completed",
                summary or "Completed",
                agent_id="orchestrator",
                data={"status": status},
            )
        elif status == "cancelled":
            await svc.events.emit(execution_id, "workflow.cancelled", summary or "Cancelled", agent_id="orchestrator")
        elif status in TERMINAL_STATUSES:
            await svc.events.emit(
                execution_id,
                "workflow.failed",
                summary or error or status,
                agent_id="orchestrator",
                data={"status": status, "error": error},
            )

    async def can_retry(self, execution_id: str, workflow: str) -> bool:
        snap = await self.graphs[workflow].aget_state(self._config(execution_id))
        return bool(snap.next)

    async def snapshot(self, execution_id: str, workflow: str) -> dict[str, Any]:
        snap = await self.graphs[workflow].aget_state(self._config(execution_id))
        return {"next": list(snap.next), "values": snap.values or {}}

    def cancel_local(self, execution_id: str) -> bool:
        task = self.tasks.get(execution_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


class Worker:
    """Claims queued/resuming executions from the database and runs them."""

    def __init__(self, engine: ExecutionEngine, concurrency: int = 4) -> None:
        self.engine = engine
        self.id = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        self.sem = asyncio.Semaphore(concurrency)
        self._stop = asyncio.Event()
        self._last_housekeeping = 0.0

    async def claim(self) -> str | None:
        db = self.engine.svc.db
        async with db.session() as s:
            candidate = await s.scalar(
                select(Execution.id)
                .where(Execution.status.in_(("queued", "resuming")), Execution.claimed_by.is_(None))
                .order_by(Execution.created_at)
                .limit(1)
            )
            if candidate is None:
                return None
            result = await s.execute(
                update(Execution)
                .where(Execution.id == candidate, Execution.claimed_by.is_(None))
                .values(claimed_by=self.id)
            )
            return candidate if result.rowcount == 1 else None  # type: ignore[attr-defined]

    async def _run_one(self, execution_id: str) -> None:
        async with self.sem:
            task = asyncio.current_task()
            assert task is not None
            self.engine.tasks[execution_id] = task
            try:
                await self.engine.run(execution_id)
            except asyncio.CancelledError:
                async with self.engine.svc.db.session() as s:
                    await s.execute(
                        update(Execution)
                        .where(Execution.id == execution_id)
                        .values(status="cancelled", finished_at=utcnow(), claimed_by=None)
                    )
                await self.engine.svc.events.emit(
                    execution_id, "workflow.cancelled", "Cancelled", agent_id="orchestrator"
                )
            finally:
                self.engine.tasks.pop(execution_id, None)

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        running: set[asyncio.Task[None]] = set()
        while not self._stop.is_set():
            try:
                if loop.time() - self._last_housekeeping > 300:
                    self._last_housekeeping = loop.time()
                    await self.housekeeping()
                execution_id = await self.claim() if not self.sem.locked() else None
                if execution_id:
                    t = asyncio.create_task(self._run_one(execution_id))
                    running.add(t)
                    t.add_done_callback(running.discard)
                    continue
            except Exception:
                log.exception("worker loop error")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self.engine.svc.settings.worker_poll_seconds)
        for t in running:
            t.cancel()

    def stop(self) -> None:
        self._stop.set()

    async def housekeeping(self) -> None:
        """Retention and stall detection."""
        svc = self.engine.svc
        s_ = svc.settings
        await asyncio.to_thread(svc.workspaces.purge_older_than, s_.workspace_retention_hours)
        await svc.memory.purge_history(s_.history_retention_days)
        cutoff = utcnow() - timedelta(days=s_.event_retention_days)
        async with svc.db.session() as s:
            old = select(Execution.id).where(Execution.finished_at < cutoff)
            from sqlalchemy import delete

            await s.execute(delete(ExecutionEvent).where(ExecutionEvent.execution_id.in_(old)))
        # Stalled: running, owned by no live local task, and silent for longer than a node may run.
        stall = utcnow() - timedelta(seconds=s_.node_timeout_seconds + 120)
        async with svc.db.session() as s:
            rows = list(await s.scalars(select(Execution).where(Execution.status == "running")))
            for ex in rows:
                if ex.id in self.engine.tasks:
                    continue
                last = await s.scalar(
                    select(func.max(ExecutionEvent.created_at)).where(ExecutionEvent.execution_id == ex.id)
                )
                if last is not None and last.tzinfo is None:
                    from datetime import UTC

                    last = last.replace(tzinfo=UTC)
                if last is None or last < stall:
                    ex.status, ex.error, ex.claimed_by = "failed", "Stalled: no progress; retry to resume", None
                    ex.finished_at = utcnow()
