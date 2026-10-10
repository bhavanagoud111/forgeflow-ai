"""FastAPI application."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from forgeflow import __version__
from forgeflow.api import errors
from forgeflow.api.routes import approvals, executions, repositories, slack, system
from forgeflow.config import Settings, get_settings
from forgeflow.container import Container, build_container
from forgeflow.db.models import Repository
from forgeflow.orchestration.engine import Worker
from forgeflow.security.ratelimit import RateLimiter

log = logging.getLogger("forgeflow")

DESCRIPTION = """
ForgeFlow AI coordinates specialised agents (analysis, planning, code generation, debugging,
review, verification and pull requests) through LangGraph workflows with persistent
checkpoints, sandboxed execution and human approval gates.

All endpoints except `/api/health` and the Slack webhooks require `Authorization: Bearer <token>`.
Errors use the shape `{"error": {"code", "message", "details"}}`.
"""


async def seed_sample_repositories(c: Container) -> None:
    """Register bundled sample repositories as local repositories (development convenience)."""
    for root in c.services.settings.local_repo_roots:
        if not root.is_dir():
            continue
        for path in sorted(p for p in root.iterdir() if p.is_dir()):
            name = f"local/{path.name}"
            async with c.services.db.session() as s:
                if await s.scalar(select(Repository).where(Repository.full_name == name)) is None:
                    s.add(
                        Repository(
                            provider="local",
                            full_name=name,
                            local_path=str(path.resolve()),
                            description="Bundled sample repository",
                        )
                    )


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        c = container or await build_container(settings)
        app.state.container = c
        app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute, settings.redis_url)
        if settings.environment != "production":
            await seed_sample_repositories(c)
        worker_task = None
        worker = None
        if settings.embedded_worker:
            worker = Worker(c.engine, settings.max_parallel_tasks)
            worker_task = asyncio.create_task(worker.run_forever())
        try:
            yield
        finally:
            if worker is not None and worker_task is not None:
                worker.stop()
                await asyncio.wait_for(worker_task, timeout=10)
            if container is None:
                await c.close()

    app = FastAPI(title="ForgeFlow AI", version=__version__, description=DESCRIPTION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    errors.install(app)
    for module in (system, executions, repositories, approvals, slack):
        app.include_router(module.router)
    return app
