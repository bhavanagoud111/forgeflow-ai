"""MCP server exposing ForgeFlow to MCP-compatible clients (IDEs, assistants).

Runs over stdio as a configured ForgeFlow user (``FORGEFLOW_MCP_TOKEN``). Read tools are
available to every role; ``start_execution`` requires the operator role. Executions
started over MCP still stop at the human approval gate before any external write.

    uv run forgeflow-mcp
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from forgeflow.config import get_settings
from forgeflow.container import Container, build_container
from forgeflow.db.models import Execution, Repository, User
from forgeflow.operations import OperationError, create_execution
from forgeflow.repository.indexer import analyze_repository
from forgeflow.schemas import Workflow
from forgeflow.security.auth import Role, hash_token


def build_mcp_server(c: Container, user: User) -> MCPServer:
    server = MCPServer(
        name="forgeflow",
        instructions="ForgeFlow AI: inspect repositories and executions, and "
        "start agent workflows. Consequential actions require human approval in ForgeFlow.",
    )
    role = Role[user.role]
    actor = f"mcp:{user.name} ({user.id})"

    @server.tool(description="List repositories connected to ForgeFlow.")
    async def list_repositories() -> list[dict[str, Any]]:
        async with c.services.db.session() as s:
            rows = list(await s.scalars(select(Repository).order_by(Repository.full_name)))
        return [
            {"id": r.id, "name": r.full_name, "provider": r.provider, "analyzed": r.analyzed_at is not None}
            for r in rows
        ]

    @server.tool(description="Search a local repository's code with ForgeFlow's retrieval index.")
    async def search_repository(repository_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        async with c.services.db.session() as s:
            repo = await s.get(Repository, repository_id)
        if repo is None:
            raise ValueError("repository not found")
        if repo.provider != "local" or not repo.local_path:
            raise ValueError("search is available for local repositories; use a workflow for GitHub repositories")
        _, index = await asyncio.to_thread(analyze_repository, Path(repo.local_path))
        return [h.model_dump() for h in index.search(query, max(1, min(limit, 20)))]

    @server.tool(description="Get the status, summary and outcome of an execution.")
    async def get_execution(execution_id: str) -> dict[str, Any]:
        async with c.services.db.session() as s:
            ex = await s.get(Execution, execution_id)
        if ex is None:
            raise ValueError("execution not found")
        report = ex.report or {}
        return {
            "id": ex.id,
            "workflow": ex.workflow,
            "status": ex.status,
            "current_node": ex.current_node,
            "summary": ex.summary,
            "error": ex.error,
            "outcome": report.get("outcome"),
            "changed": report.get("changed"),
            "pr": report.get("pr"),
        }

    @server.tool(description="List recent executions, optionally filtered by status.")
    async def list_executions(status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        q = select(Execution).order_by(Execution.created_at.desc()).limit(max(1, min(limit, 100)))
        if status:
            q = q.where(Execution.status == status)
        async with c.services.db.session() as s:
            rows = list(await s.scalars(q))
        return [{"id": e.id, "workflow": e.workflow, "status": e.status, "request": e.request[:200]} for e in rows]

    @server.tool(
        description="Start a workflow (feature, bug_investigation, test_generation, repo_onboarding). "
        "Requires the operator role. Publishing still needs human approval."
    )
    async def start_execution(repository_id: str, workflow: str, request: str) -> dict[str, Any]:
        if role < Role.operator:
            raise PermissionError("operator role required")
        try:
            wf = Workflow(workflow)
        except ValueError as exc:
            raise ValueError(f"unknown workflow {workflow}") from exc
        if wf == Workflow.code_review:
            raise ValueError("start code reviews from the API or Slack")
        try:
            ex = await create_execution(
                c, repository_id=repository_id, workflow=wf, request=request, params={}, actor=actor, source="mcp"
            )
        except OperationError as exc:
            raise ValueError(exc.message) from exc
        return {"id": ex.id, "status": ex.status}

    return server


async def _amain() -> None:
    token = os.environ.get("FORGEFLOW_MCP_TOKEN")
    if not token:
        raise SystemExit("FORGEFLOW_MCP_TOKEN is required")
    c = await build_container(get_settings())
    try:
        async with c.services.db.session() as s:
            user = await s.scalar(select(User).where(User.token_hash == hash_token(token)))
        if user is None:
            raise SystemExit("FORGEFLOW_MCP_TOKEN does not match a ForgeFlow user")
        await build_mcp_server(c, user).run_stdio_async()
    finally:
        await c.close()


def main() -> None:
    asyncio.run(_amain())
