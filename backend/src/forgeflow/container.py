"""Wires services, the checkpointer and the execution engine together."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass

from sqlalchemy import select

from forgeflow.agents.base import Services
from forgeflow.config import Settings
from forgeflow.db.models import User
from forgeflow.db.session import Database
from forgeflow.events.bus import EventBus
from forgeflow.integrations.github import GitHubClient
from forgeflow.llm import build_llm
from forgeflow.memory.store import MemoryStore
from forgeflow.orchestration.engine import ExecutionEngine, open_checkpointer
from forgeflow.security.auth import hash_token
from forgeflow.telemetry import Recorder, configure_tracing
from forgeflow.workspace.manager import WorkspaceManager
from forgeflow.workspace.sandbox import build_sandbox


@dataclass
class Container:
    services: Services
    engine: ExecutionEngine
    stack: AsyncExitStack

    async def close(self) -> None:
        await self.stack.aclose()
        await self.services.db.dispose()


async def build_container(settings: Settings, *, create_tables: bool | None = None) -> Container:
    configure_tracing(settings)
    db = Database(settings.database_url)
    # Development and tests create tables directly; production schemas are managed by Alembic.
    if create_tables if create_tables is not None else settings.environment != "production":
        await db.create_all()
    events = EventBus(db)
    services = Services(
        settings=settings,
        db=db,
        events=events,
        recorder=Recorder(db, events),
        llm=build_llm(settings),
        workspaces=WorkspaceManager(settings.workspace_root, settings.max_file_bytes),
        sandbox=build_sandbox(settings),
        github=GitHubClient(settings),
        memory=MemoryStore(db),
    )
    stack = AsyncExitStack()
    checkpointer = await open_checkpointer(settings.checkpoint_url, stack)
    engine = ExecutionEngine(services, checkpointer)
    if settings.admin_token:
        await ensure_user(db, "admin", "admin", settings.admin_token.get_secret_value())
    return Container(services=services, engine=engine, stack=stack)


async def ensure_user(db: Database, name: str, role: str, token: str) -> None:
    h = hash_token(token)
    async with db.session() as s:
        existing = await s.scalar(select(User).where(User.token_hash == h))
        if existing is None:
            s.add(User(name=name, role=role, token_hash=h))
