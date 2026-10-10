"""Operations shared by the HTTP API, Slack and MCP entry points.

Authorization is enforced by callers; these functions enforce state rules (what may
happen to an execution or approval in its current state) and write audit records.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from forgeflow.container import Container
from forgeflow.db.models import Approval, AuditLog, Execution, Repository, utcnow
from forgeflow.schemas import TERMINAL_STATUSES, Workflow
from forgeflow.security.redaction import redact_obj


class OperationError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


async def _audit(c: Container, actor: str, action: str, target: str | None, **details: Any) -> None:
    async with c.services.db.session() as s:
        s.add(AuditLog(actor=actor, action=action, target=target, details=redact_obj(details)))


async def create_execution(
    c: Container,
    *,
    repository_id: str,
    workflow: Workflow,
    request: str,
    params: dict[str, Any],
    actor: str,
    source: str = "api",
) -> Execution:
    request = request.strip()
    if workflow in (Workflow.feature, Workflow.bug_investigation, Workflow.test_generation) and len(request) < 5:
        raise OperationError(422, "validation_error", "This workflow needs a request of at least 5 characters")
    allowed = {"base_branch", "issue", "pr_number", "diff", "max_debug_attempts"}
    unknown = set(params) - allowed
    if unknown:
        raise OperationError(422, "validation_error", f"Unknown params: {sorted(unknown)}")
    if "max_debug_attempts" in params:
        params["max_debug_attempts"] = max(
            0, min(int(params["max_debug_attempts"]), c.services.settings.max_debug_attempts)
        )
    async with c.services.db.session() as s:
        repo = await s.get(Repository, repository_id)
        if repo is None:
            raise OperationError(404, "not_found", "Repository not found")
        if workflow == Workflow.code_review and not (params.get("pr_number") or params.get("diff")):
            raise OperationError(422, "validation_error", "code_review needs params.pr_number or params.diff")
        ex = Execution(
            workflow=workflow.value,
            repository_id=repo.id,
            request=request,
            params=params,
            created_by=actor,
            source=source,
        )
        s.add(ex)
        await s.flush()
    await _audit(c, actor, "execution.create", ex.id, workflow=workflow.value, repository=repo.full_name, source=source)
    return ex


async def cancel_execution(c: Container, execution_id: str, actor: str) -> Execution:
    async with c.services.db.session() as s:
        ex = await s.get(Execution, execution_id)
        if ex is None:
            raise OperationError(404, "not_found", "Execution not found")
        if ex.status in TERMINAL_STATUSES:
            raise OperationError(409, "conflict", f"Execution is already {ex.status}")
        ex.cancel_requested = True
        if ex.status in ("queued", "awaiting_approval", "resuming") and ex.claimed_by is None:
            ex.status, ex.finished_at, ex.summary = "cancelled", utcnow(), f"Cancelled by {actor}"
            await s.execute(
                update(Approval)
                .where(Approval.execution_id == ex.id, Approval.status == "pending")
                .values(status="expired", decided_at=utcnow())
            )
            emit = True
        else:
            emit = False
    c.engine.cancel_local(execution_id)
    if emit:
        await c.services.events.emit(
            execution_id, "workflow.cancelled", f"Cancelled by {actor}", agent_id="orchestrator"
        )
    await _audit(c, actor, "execution.cancel", execution_id)
    async with c.services.db.session() as s:
        result = await s.get(Execution, execution_id)
        assert result is not None
        return result


async def retry_execution(c: Container, execution_id: str, actor: str) -> Execution:
    async with c.services.db.session() as s:
        ex = await s.get(Execution, execution_id)
        if ex is None:
            raise OperationError(404, "not_found", "Execution not found")
        if ex.status != "failed" or ex.report is not None:
            raise OperationError(409, "conflict", "Only executions that failed with an error can be retried")
    if not await c.engine.can_retry(execution_id, ex.workflow):
        raise OperationError(409, "conflict", "No checkpoint to resume from")
    async with c.services.db.session() as s:
        await s.execute(
            update(Execution)
            .where(Execution.id == execution_id)
            .values(
                status="resuming",
                resume_payload={"retry": True},
                claimed_by=None,
                finished_at=None,
                cancel_requested=False,
            )
        )
    await _audit(c, actor, "execution.retry", execution_id)
    async with c.services.db.session() as s:
        result = await s.get(Execution, execution_id)
        assert result is not None
        return result


async def decide_approval(
    c: Container, approval_id: str, *, approved: bool, actor: str, comment: str | None
) -> Approval:
    async with c.services.db.session() as s:
        approval = await s.get(Approval, approval_id)
        if approval is None:
            raise OperationError(404, "not_found", "Approval not found")
        if approval.status != "pending":
            raise OperationError(409, "conflict", f"Approval is already {approval.status}")
        ex = await s.get(Execution, approval.execution_id)
        if ex is None or ex.status != "awaiting_approval":
            raise OperationError(409, "conflict", "Execution is not waiting for approval")
        approval.status = "approved" if approved else "rejected"
        approval.decided_by = actor
        approval.decision_comment = comment
        approval.decided_at = utcnow()
        ex.status = "resuming"
        ex.claimed_by = None
        ex.resume_payload = {"decision": approval.status, "by": actor, "comment": comment}
    await c.services.events.emit(
        approval.execution_id,
        "approval.decided",
        f"{approval.status} by {actor}",
        agent_id="orchestrator",
        data={"approval_id": approval_id, "decision": approval.status, "comment": comment},
    )
    await _audit(c, actor, f"approval.{approval.status}", approval_id, execution_id=approval.execution_id)
    return approval


async def repository_by_name(c: Container, name: str) -> Repository | None:
    async with c.services.db.session() as s:
        return await s.scalar(select(Repository).where(Repository.full_name == name))
