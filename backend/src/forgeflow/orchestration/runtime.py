"""Per-invocation runtime context and the step wrapper used by every node."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update

from forgeflow.agents.base import Services
from forgeflow.db.models import Execution
from forgeflow.repository.indexer import RepositoryIndex
from forgeflow.telemetry import RunHandle


class ExecutionCancelled(Exception):
    pass


@dataclass
class Ctx:
    svc: Services
    # Process-local caches (never checkpointed): repository indexes keyed by workspace id.
    indexes: dict[str, RepositoryIndex] = field(default_factory=dict)


async def check_cancelled(svc: Services, execution_id: str) -> None:
    async with svc.db.session() as s:
        row = await s.get(Execution, execution_id)
        if row is not None and row.cancel_requested:
            raise ExecutionCancelled("cancelled by user")


@asynccontextmanager
async def step(
    ctx: Ctx, execution_id: str, agent_id: str, node: str, *, attempt: int = 1, message: str = ""
) -> AsyncIterator[RunHandle]:
    """Cancellation check, current-node bookkeeping, timeout and agent-run recording."""
    svc = ctx.svc
    await check_cancelled(svc, execution_id)
    async with svc.db.session() as s:
        await s.execute(update(Execution).where(Execution.id == execution_id).values(current_node=node))
    async with svc.recorder.agent_run(execution_id, agent_id, node, attempt=attempt, message=message) as run:
        async with asyncio.timeout(svc.settings.node_timeout_seconds):
            yield run


def dump(model: Any) -> Any:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model
