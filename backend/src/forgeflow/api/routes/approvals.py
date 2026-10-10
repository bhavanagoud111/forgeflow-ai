from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from forgeflow.api.deps import ContainerDep, Operator, PageDep, Viewer
from forgeflow.api.errors import APIError
from forgeflow.api.schemas import ApprovalDecision, ApprovalOut, Page
from forgeflow.db.models import Approval
from forgeflow.operations import OperationError, decide_approval

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalOut], summary="Approvals (pending first)")
async def list_approvals(
    c: ContainerDep, _: Viewer, page: PageDep, status: Annotated[str | None, Query()] = None
) -> dict[str, Any]:
    q = select(Approval)
    cq = select(func.count(Approval.id))
    if status:
        q, cq = q.where(Approval.status == status), cq.where(Approval.status == status)
    async with c.services.db.session() as s:
        total = await s.scalar(cq) or 0
        rows = list(
            await s.scalars(
                q.order_by((Approval.status != "pending"), Approval.created_at.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        )
    return {"items": rows, "total": total, "limit": page.limit, "offset": page.offset}


async def _decide(c: ContainerDep, approval_id: str, approved: bool, actor: str, comment: str | None) -> Approval:
    try:
        return await decide_approval(c, approval_id, approved=approved, actor=actor, comment=comment)
    except OperationError as exc:
        raise APIError(exc.status, exc.code, exc.message) from exc


@router.post("/{approval_id}/approve", response_model=ApprovalOut, summary="Approve a pending action")
async def approve(approval_id: str, c: ContainerDep, p: Operator, body: ApprovalDecision | None = None) -> Approval:
    return await _decide(c, approval_id, True, p.actor, body.comment if body else None)


@router.post("/{approval_id}/reject", response_model=ApprovalOut, summary="Reject a pending action")
async def reject(approval_id: str, c: ContainerDep, p: Operator, body: ApprovalDecision | None = None) -> Approval:
    return await _decide(c, approval_id, False, p.actor, body.comment if body else None)
