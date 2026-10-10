from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from forgeflow.api.app import create_app
from forgeflow.config import REPO_ROOT, Settings
from forgeflow.container import Container, build_container, ensure_user
from forgeflow.db.models import Execution
from forgeflow.schemas import TERMINAL_STATUSES

SAMPLE_REPO = REPO_ROOT / "examples" / "sample-repos" / "taskboard-api"
ADMIN = "test-admin-token"
OPERATOR = "test-operator-token"
VIEWER = "test-viewer-token"


def make_settings(tmp: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "database_url": f"sqlite+aiosqlite:///{tmp}/app.db",
        "checkpoint_url": f"{tmp}/checkpoints.db",
        "workspace_root": tmp / "workspaces",
        "admin_token": SecretStr(ADMIN),
        "llm_provider": "demo",
        "sandbox_mode": "local",
        "embedded_worker": True,
        "worker_poll_seconds": 0.05,
        "local_repo_roots": [SAMPLE_REPO.parent],
        "github_token": None,
        "slack_signing_secret": None,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    c = await build_container(settings)
    await ensure_user(c.services.db, "operator", "operator", OPERATOR)
    await ensure_user(c.services.db, "viewer", "viewer", VIEWER)
    yield c
    await c.close()


@pytest.fixture
async def client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, container=container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {ADMIN}"}
        ) as c:
            yield c


async def wait_for_status(
    container: Container, execution_id: str, statuses: set[str] | None = None, timeout: float = 60
) -> Execution:
    statuses = statuses or set(TERMINAL_STATUSES) | {"awaiting_approval"}
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with container.services.db.session() as s:
            ex = await s.get(Execution, execution_id)
        assert ex is not None
        if ex.status in statuses and ex.claimed_by is None:
            return ex
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {statuses}; status={ex.status} error={ex.error}")
        await asyncio.sleep(0.1)


async def sample_repo_id(client: httpx.AsyncClient) -> str:
    items = (await client.get("/api/repositories")).json()["items"]
    return next(r["id"] for r in items if r["full_name"] == "local/taskboard-api")
