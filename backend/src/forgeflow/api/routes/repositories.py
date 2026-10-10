from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from forgeflow.api.deps import Admin, ContainerDep, Operator, PageDep, Viewer, audit
from forgeflow.api.errors import APIError
from forgeflow.api.schemas import ExecutionOut, Page, RepositoryConnect, RepositoryDetail, RepositoryOut
from forgeflow.db.models import Repository
from forgeflow.integrations.github import GitHubError, GitHubNotConfigured, parse_repo
from forgeflow.operations import OperationError, create_execution
from forgeflow.repository.indexer import iter_files
from forgeflow.schemas import Workflow

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def _out(r: Repository) -> dict[str, Any]:
    data = {k: getattr(r, k) for k in RepositoryOut.model_fields if hasattr(r, k)}
    data["summary"] = (r.analysis or {}).get("summary")
    return data


async def _get(c: ContainerDep, repository_id: str) -> Repository:
    async with c.services.db.session() as s:
        repo = await s.get(Repository, repository_id)
    if repo is None:
        raise APIError(404, "not_found", "Repository not found")
    return repo


def allowed_local_path(c: ContainerDep, raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    for root in c.services.settings.local_repo_roots:
        root = root.resolve()
        if path == root or root in path.parents:
            if path.is_dir():
                return path
    raise APIError(403, "forbidden", "Local path is not under an allowed repository root")


@router.get("", response_model=Page[RepositoryOut], summary="Connected repositories")
async def list_repositories(c: ContainerDep, _: Viewer, page: PageDep) -> dict[str, Any]:
    async with c.services.db.session() as s:
        total = await s.scalar(select(func.count(Repository.id))) or 0
        rows = list(
            await s.scalars(select(Repository).order_by(Repository.created_at).limit(page.limit).offset(page.offset))
        )
    return {"items": [_out(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.post("/connect", response_model=RepositoryOut, status_code=201, summary="Connect a repository")
async def connect(body: RepositoryConnect, c: ContainerDep, p: Operator) -> dict[str, Any]:
    if body.provider == "github":
        if not body.full_name:
            raise APIError(422, "validation_error", "full_name is required for GitHub repositories")
        try:
            name = parse_repo(body.full_name)
            meta = await c.services.github.get_repo(name)
        except ValueError as exc:
            raise APIError(422, "validation_error", str(exc)) from exc
        except GitHubNotConfigured as exc:
            raise APIError(409, "github_not_configured", str(exc)) from exc
        except GitHubError as exc:
            raise APIError(502 if (exc.status or 500) >= 500 else 404, "github_error", str(exc)) from exc
        repo = Repository(
            provider="github",
            full_name=meta["full_name"],
            default_branch=meta["default_branch"],
            description=meta.get("description"),
        )
    else:
        if not body.path:
            raise APIError(422, "validation_error", "path is required for local repositories")
        path = allowed_local_path(c, body.path)
        repo = Repository(
            provider="local",
            full_name=f"local/{path.name}",
            local_path=str(path),
            default_branch="main",
            description=f"Local repository at {path.name}",
        )
    async with c.services.db.session() as s:
        if await s.scalar(select(Repository).where(Repository.full_name == repo.full_name)):
            raise APIError(409, "conflict", f"{repo.full_name} is already connected")
        s.add(repo)
    await audit(c, p.actor, "repository.connect", repo.id, name=repo.full_name, provider=repo.provider)
    return _out(repo)


@router.get("/{repository_id}", response_model=RepositoryDetail, summary="Repository detail with memory")
async def get(repository_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    repo = await _get(c, repository_id)
    memory = await c.services.memory.repository(repo.id)
    history = await c.services.memory.history(repo.id, limit=30)
    data = _out(repo)
    data.update(
        analysis=(repo.analysis or {}).get("analysis"),
        memory=memory,
        history=[
            {
                "kind": h.kind,
                "title": h.title,
                "content": h.content,
                "execution_id": h.execution_id,
                "created_at": h.created_at,
            }
            for h in history
        ],
    )
    return data


@router.post(
    "/{repository_id}/analyze",
    response_model=ExecutionOut,
    status_code=202,
    summary="Run the repository onboarding workflow",
)
async def analyze(repository_id: str, c: ContainerDep, p: Operator) -> dict[str, Any]:
    repo = await _get(c, repository_id)
    try:
        ex = await create_execution(
            c,
            repository_id=repo.id,
            workflow=Workflow.repo_onboarding,
            request=f"Analyse {repo.full_name}",
            params={},
            actor=p.actor,
        )
    except OperationError as exc:
        raise APIError(exc.status, exc.code, exc.message) from exc
    data = {k: getattr(ex, k) for k in ExecutionOut.model_fields if hasattr(ex, k)}
    data["repository_name"] = repo.full_name
    return data


@router.get("/{repository_id}/tree", summary="Source tree (paths)")
async def tree(repository_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    repo = await _get(c, repository_id)
    if repo.provider == "local":
        assert repo.local_path
        files = await asyncio.to_thread(iter_files, Path(repo.local_path))
        return {"files": files, "source": "local"}
    try:
        return {"files": await c.services.github.get_tree(repo.full_name, repo.default_branch), "source": "github"}
    except GitHubError as exc:
        raise APIError(502, "github_error", str(exc)) from exc


@router.get("/{repository_id}/files", summary="Read one file from the default branch")
async def file(repository_id: str, path: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    from forgeflow.schemas import validate_rel_path

    repo = await _get(c, repository_id)
    try:
        rel = validate_rel_path(path)
    except ValueError as exc:
        raise APIError(422, "validation_error", str(exc)) from exc
    if repo.provider == "local":
        assert repo.local_path
        root = Path(repo.local_path).resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file() or target.stat().st_size > 500_000:
            raise APIError(404, "not_found", "File not found")
        return {"path": rel, "content": target.read_text(errors="replace")}
    try:
        return {"path": rel, "content": await c.services.github.get_file(repo.full_name, rel, repo.default_branch)}
    except GitHubError as exc:
        raise APIError(404, "not_found", str(exc)) from exc


async def _github_list(c: ContainerDep, repository_id: str, kind: str) -> dict[str, Any]:
    repo = await _get(c, repository_id)
    if repo.provider != "github":
        return {"items": [], "note": "Issues and pull requests are only available for GitHub repositories."}
    try:
        if kind == "issues":
            items = await c.services.github.list_issues(repo.full_name)
            return {
                "items": [
                    {
                        "number": i["number"],
                        "title": i["title"],
                        "state": i["state"],
                        "user": i["user"]["login"],
                        "url": i["html_url"],
                        "labels": [lb["name"] for lb in i["labels"]],
                        "updated_at": i["updated_at"],
                    }
                    for i in items
                ]
            }
        if kind == "pulls":
            items = await c.services.github.list_pulls(repo.full_name)
            return {
                "items": [
                    {
                        "number": pr["number"],
                        "title": pr["title"],
                        "state": pr["state"],
                        "user": pr["user"]["login"],
                        "url": pr["html_url"],
                        "draft": pr.get("draft"),
                        "head": pr["head"]["ref"],
                        "updated_at": pr["updated_at"],
                    }
                    for pr in items
                ]
            }
        branches = await c.services.github.list_branches(repo.full_name)
        return {
            "items": [{"name": b["name"], "sha": b["commit"]["sha"], "protected": b.get("protected")} for b in branches]
        }
    except GitHubNotConfigured as exc:
        return {"items": [], "note": str(exc)}
    except GitHubError as exc:
        raise APIError(502, "github_error", str(exc)) from exc


@router.get("/{repository_id}/issues", summary="Open issues (GitHub)")
async def issues(repository_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    return await _github_list(c, repository_id, "issues")


@router.get("/{repository_id}/pulls", summary="Open pull requests (GitHub)")
async def pulls(repository_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    return await _github_list(c, repository_id, "pulls")


@router.get("/{repository_id}/branches", summary="Branches (GitHub)")
async def branches(repository_id: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    return await _github_list(c, repository_id, "branches")


@router.get("/{repository_id}/ci/{ref}", summary="CI status for a ref (GitHub)")
async def ci(repository_id: str, ref: str, c: ContainerDep, _: Viewer) -> dict[str, Any]:
    repo = await _get(c, repository_id)
    if repo.provider != "github":
        raise APIError(409, "conflict", "CI status is only available for GitHub repositories")
    try:
        return await c.services.github.ci_status(repo.full_name, ref)
    except GitHubError as exc:
        raise APIError(502, "github_error", str(exc)) from exc


@router.delete("/{repository_id}/memory", status_code=204, summary="Delete repository and historical memory")
async def forget(repository_id: str, c: ContainerDep, p: Admin) -> None:
    repo = await _get(c, repository_id)
    await c.services.memory.forget_repository(repo.id)
    await audit(c, p.actor, "memory.delete", repo.id)
