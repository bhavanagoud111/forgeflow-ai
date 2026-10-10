"""Isolated per-execution workspaces.

Each execution gets its own directory containing a copy of the repository (never the
user's checkout), initialised as a fresh git repository with a baseline commit and a
``forgeflow/<execution>`` branch. GitHub repositories are fetched as a tarball for a
pinned commit, so no credentials or remote configuration ever enter the workspace.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

from forgeflow.schemas import FileEdit, validate_rel_path

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    "dist",
    "build",
    ".tox",
    ".forgeflow",
}
MAX_REPO_BYTES = 200 * 1024 * 1024
ARTIFACT_PATTERNS = {
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "node_modules/",
    ".coverage",
    "coverage/",
    ".next/",
    "*.egg-info/",
}


class WorkspaceError(RuntimeError):
    pass


class EditError(WorkspaceError):
    pass


@dataclass
class Workspace:
    id: str
    path: Path
    branch: str
    base_ref: str = "forgeflow-base"


def _git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "ForgeFlow",
        "GIT_AUTHOR_EMAIL": "forgeflow@localhost",
        "GIT_COMMITTER_NAME": "ForgeFlow",
        "GIT_COMMITTER_EMAIL": "forgeflow@localhost",
    }


class WorkspaceManager:
    def __init__(self, root: Path, max_file_bytes: int = 200_000) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_bytes

    def path_for(self, workspace_id: str) -> Path:
        p = (self.root / workspace_id).resolve()
        if p.parent != self.root:
            raise WorkspaceError("invalid workspace id")
        return p

    def get(self, workspace_id: str, branch: str) -> Workspace:
        p = self.path_for(workspace_id)
        if not (p / "repo").is_dir():
            raise WorkspaceError(f"workspace {workspace_id} no longer exists")
        return Workspace(id=workspace_id, path=p / "repo", branch=branch)

    # ------------------------------------------------------------------ creation

    async def create_from_local(self, workspace_id: str, source: Path, branch: str) -> Workspace:
        source = source.resolve()
        if not source.is_dir():
            raise WorkspaceError(f"source repository not found: {source}")
        dest = self._fresh_dir(workspace_id)
        await asyncio.to_thread(self._copy_tree, source, dest / "repo")
        return await self._init_git(workspace_id, dest / "repo", branch)

    async def create_from_tarball(self, workspace_id: str, data: bytes, branch: str) -> Workspace:
        dest = self._fresh_dir(workspace_id)
        await asyncio.to_thread(self._extract_tarball, data, dest / "repo")
        return await self._init_git(workspace_id, dest / "repo", branch)

    def _fresh_dir(self, workspace_id: str) -> Path:
        dest = self.path_for(workspace_id)
        if dest.exists():
            shutil.rmtree(dest)
        (dest / "home").mkdir(parents=True)
        return dest

    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> None:
        total = 0
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            rel = Path(dirpath).relative_to(src)
            (dst / rel).mkdir(parents=True, exist_ok=True)
            for name in filenames:
                s = Path(dirpath) / name
                if s.is_symlink() or not s.is_file():
                    continue  # symlinks could point outside the repository
                total += s.stat().st_size
                if total > MAX_REPO_BYTES:
                    raise WorkspaceError("repository exceeds workspace size limit")
                shutil.copy2(s, dst / rel / name)

    @staticmethod
    def _extract_tarball(data: bytes, dst: Path) -> None:
        dst.mkdir(parents=True)
        total = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if len(parts) < 2 or not (member.isfile() or member.isdir()):
                    continue  # skip the archive root, links and devices
                rel = Path(*parts[1:])
                if any(p in IGNORED_DIRS for p in rel.parts) or rel.is_absolute() or ".." in rel.parts:
                    continue
                target = dst / rel
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += member.size
                if total > MAX_REPO_BYTES:
                    raise WorkspaceError("repository exceeds workspace size limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(member)
                if f is not None:
                    target.write_bytes(f.read())

    async def _init_git(self, workspace_id: str, repo: Path, branch: str) -> Workspace:
        ws = Workspace(id=workspace_id, path=repo, branch=branch)
        await self.git(ws, "init", "-q", "-b", "main")
        # Build and test artifacts produced inside the sandbox must never become part of a change.
        (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (repo / ".git" / "info" / "exclude").write_text("\n".join(sorted(ARTIFACT_PATTERNS)) + "\n")
        await self.git(ws, "add", "-A")
        await self.git(ws, "commit", "-q", "--allow-empty", "--no-verify", "-m", "ForgeFlow baseline")
        await self.git(ws, "tag", ws.base_ref)
        await self.git(ws, "checkout", "-q", "-b", branch)
        return ws

    # ------------------------------------------------------------------ git helpers

    async def git(self, ws: Workspace, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            *args,
            cwd=ws.path,
            env=_git_env(ws.path.parent / "home"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise WorkspaceError(f"git {args[0]} failed: {err.decode(errors='replace')[:500]}")
        return out.decode(errors="replace")

    async def diff(self, ws: Workspace) -> str:
        await self.git(ws, "add", "-A")
        return await self.git(ws, "diff", "--cached", "--no-color", "--no-ext-diff", ws.base_ref)

    async def changed_files(self, ws: Workspace) -> list[dict[str, str]]:
        await self.git(ws, "add", "-A")
        out = await self.git(ws, "diff", "--cached", "--name-status", "--no-renames", ws.base_ref)
        result = []
        for line in out.splitlines():
            status, _, path = line.partition("\t")
            result.append({"status": {"A": "added", "M": "modified", "D": "deleted"}.get(status, status), "path": path})
        return result

    async def commit(self, ws: Workspace, message: str) -> str:
        await self.git(ws, "add", "-A")
        await self.git(ws, "commit", "-q", "--allow-empty", "--no-verify", "-m", message)
        return (await self.git(ws, "rev-parse", "HEAD")).strip()

    # ------------------------------------------------------------------ files

    def resolve(self, ws: Workspace, rel: str) -> Path:
        rel = validate_rel_path(rel)
        root = ws.path.resolve()
        target = (root / rel).resolve()
        if root not in target.parents:
            raise EditError(f"path escapes workspace: {rel}")
        return target

    def read_file(self, ws: Workspace, rel: str) -> str | None:
        p = self.resolve(ws, rel)
        if not p.is_file() or p.stat().st_size > self.max_file_bytes:
            return None
        try:
            return p.read_text()
        except UnicodeDecodeError:
            return None

    def apply_edits(self, ws: Workspace, edits: list[FileEdit]) -> list[str]:
        """Apply edits atomically: validate everything first, then write."""
        staged: dict[Path, str | None] = {}
        for edit in edits:
            target = self.resolve(ws, edit.path)
            current = staged[target] if target in staged else (target.read_text() if target.is_file() else None)
            if edit.operation == "create":
                if current is not None:
                    raise EditError(f"{edit.path} already exists; use replace or rewrite")
                new = edit.content
            elif edit.operation == "rewrite":
                if current is None:
                    raise EditError(f"{edit.path} does not exist")
                new = edit.content
            elif edit.operation == "delete":
                if current is None:
                    raise EditError(f"{edit.path} does not exist")
                new = None
            else:  # replace
                if current is None:
                    raise EditError(f"{edit.path} does not exist")
                assert edit.search is not None and edit.replacement is not None
                count = current.count(edit.search)
                if count != 1:
                    raise EditError(f"search text matched {count} times in {edit.path} (must match exactly once)")
                new = current.replace(edit.search, edit.replacement)
            if new is not None and len(new.encode()) > self.max_file_bytes:
                raise EditError(f"{edit.path} exceeds the maximum file size")
            staged[target] = new
        for target, content in staged.items():
            if content is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
        root = ws.path.resolve()
        return sorted({str(t.relative_to(root)) for t in staged})

    # ------------------------------------------------------------------ cleanup

    def remove(self, workspace_id: str) -> None:
        shutil.rmtree(self.path_for(workspace_id), ignore_errors=True)

    def purge_older_than(self, hours: int) -> int:
        cutoff = time.time() - hours * 3600
        removed = 0
        for child in self.root.iterdir():
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        return removed
