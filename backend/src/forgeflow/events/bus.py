"""Execution event log.

Events are appended to ``execution_events`` with a per-execution sequence number, which
is what clients use as the SSE ``Last-Event-ID`` to resume without gaps or duplicates.
The database is the source of truth; the in-process notifier only lowers latency for
SSE streams served by the same process. Streams in other processes poll.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from forgeflow.db.models import ExecutionEvent
from forgeflow.db.session import Database
from forgeflow.security.redaction import redact, redact_obj

EVENT_TYPES = frozenset(
    {
        "workflow.started",
        "workflow.resumed",
        "workflow.completed",
        "workflow.failed",
        "workflow.cancelled",
        "agent.started",
        "agent.completed",
        "agent.failed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "plan.created",
        "patch.applied",
        "test.passed",
        "test.failed",
        "review.completed",
        "verification.completed",
        "approval.required",
        "approval.decided",
        "pr.created",
        "log",
    }
)


class EventBus:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def emit(
        self,
        execution_id: str,
        type: str,
        message: str = "",
        *,
        agent_id: str | None = None,
        node: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> int:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type}")
        async with self._locks[execution_id]:
            async with self.db.session() as s:
                current = await s.scalar(
                    select(func.max(ExecutionEvent.seq)).where(ExecutionEvent.execution_id == execution_id)
                )
                seq = (current or 0) + 1
                s.add(
                    ExecutionEvent(
                        execution_id=execution_id,
                        seq=seq,
                        type=type,
                        agent_id=agent_id,
                        node=node,
                        message=redact(message)[:4000],
                        data=redact_obj(data or {}),
                    )
                )
        cond = self._conditions[execution_id]
        async with cond:
            cond.notify_all()
        return seq

    async def wait(self, execution_id: str, timeout: float) -> None:
        cond = self._conditions[execution_id]
        async with cond:
            try:
                await asyncio.wait_for(cond.wait(), timeout)
            except TimeoutError:
                pass

    async def since(self, execution_id: str, after_seq: int, limit: int = 500) -> list[ExecutionEvent]:
        async with self.db.session() as s:
            rows = await s.scalars(
                select(ExecutionEvent)
                .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.seq > after_seq)
                .order_by(ExecutionEvent.seq)
                .limit(limit)
            )
            return list(rows)
