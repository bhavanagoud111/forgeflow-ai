"""Sandbox runner service.

Runs inside its own container with no credentials, a read-only image, resource limits
and an internal-only network. It accepts allowlisted commands for workspaces on the
shared volume and executes them with the local backend (rlimits, timeout, clean env).
"""

from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from forgeflow.config import get_settings
from forgeflow.schemas import CommandResult
from forgeflow.security.command_policy import CommandRejected, validate_command
from forgeflow.workspace.sandbox import LocalSandbox

app = FastAPI(title="ForgeFlow sandbox runner", docs_url=None, redoc_url=None)


class RunRequest(BaseModel):
    workspace: str
    argv: list[str] = Field(min_length=1, max_length=40)
    timeout: int = Field(ge=1, le=1800)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=CommandResult)
async def run(req: RunRequest, authorization: str | None = Header(default=None)) -> CommandResult:
    settings = get_settings()
    expected = settings.sandbox_runner_token.get_secret_value() if settings.sandbox_runner_token else None
    if expected and not hmac.compare_digest(authorization or "", f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")
    root = settings.workspace_root.resolve()
    target = (root / req.workspace).resolve()
    if root not in target.parents or not target.is_dir():
        raise HTTPException(status_code=400, detail="invalid workspace")
    try:
        validate_command(req.argv, allow_dependency_install=settings.allow_dependency_install)
    except CommandRejected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return await LocalSandbox(settings).run(Path(target), req.argv, req.timeout)
