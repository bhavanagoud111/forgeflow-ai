"""Code Generation Agent."""

from __future__ import annotations

from forgeflow.agents.base import Services
from forgeflow.schemas import CodeContext, PatchProposal, TaskSpec
from forgeflow.security.untrusted import fence
from forgeflow.telemetry import RunHandle
from forgeflow.workspace.manager import EditError, Workspace

SYSTEM = (
    "You are the Code Generation Agent. Implement exactly one task as a list of file edits. Prefer "
    "'replace' edits whose 'search' text is copied verbatim from the current file and matches exactly once; "
    "use 'create' for new files and 'rewrite' only for small files. Follow the repository's existing style, "
    "keep public interfaces stable, add or update tests for the behaviour you change, and do not touch files "
    "unrelated to the task. Never edit CI configuration, lockfiles, secrets or environment files."
)

PROTECTED_PREFIXES = (".github/", ".git/", ".env", "secrets", ".forgeflow")
PROTECTED_SUFFIXES = (".pem", ".key", "id_rsa", ".lock", "package-lock.json")


class PatchRejected(ValueError):
    pass


def check_scope(proposal: PatchProposal, max_files: int) -> list[str]:
    """Hard policy on proposed edits. Returns warnings; raises on violations."""
    paths = {e.path for e in proposal.edits}
    if len(paths) > max_files:
        raise PatchRejected(f"patch touches {len(paths)} files (limit {max_files})")
    for p in paths:
        name = p.lower()
        if name.startswith(PROTECTED_PREFIXES) or name.endswith(PROTECTED_SUFFIXES) or "/.env" in name:
            raise PatchRejected(f"edits to protected path are not allowed: {p}")
    return []


def _file_context(svc: Services, ws: Workspace, paths: list[str]) -> str:
    parts = []
    for p in paths:
        try:
            content = svc.workspaces.read_file(ws, p)
        except EditError:
            continue
        parts.append(
            fence(
                f"current-{p.replace('/', '-')}",
                f"# {p}\n{content}" if content is not None else f"# {p}\n(file does not exist yet)",
                30_000,
            )
        )
    return "\n\n".join(parts)


async def generate(
    svc: Services,
    run: RunHandle,
    *,
    workflow: str,
    request: str,
    task: TaskSpec,
    ws: Workspace,
    relevant: list[CodeContext],
    files: list[str],
    conventions: list[str],
) -> PatchProposal:
    target_ctx = _file_context(svc, ws, task.target_files)
    excerpts = "\n\n".join(
        fence(f"ctx-{i}", f"# {c.path}:{c.start_line}\n{c.content}", 4000)
        for i, c in enumerate(relevant)
        if c.path not in task.target_files
    )
    prompt = (
        f"Overall request:\n{fence('request', request, 4000)}\n\n"
        f"Task:\n{task.model_dump_json(indent=2)}\n\n"
        f"Conventions: {'; '.join(conventions) or 'follow surrounding code'}\n\n"
        f"Target files:\n{target_ctx}\n\nOther relevant code:\n{excerpts}"
    )
    proposal = await svc.llm.structured(
        PatchProposal,
        purpose="codegen",
        system=SYSTEM,
        prompt=prompt,
        run=run,
        context={"workflow": workflow, "request": request, "task": task.model_dump(), "files": files},
    )
    proposal = proposal.model_copy(update={"task_id": task.task_id})
    check_scope(proposal, svc.settings.max_patch_files)
    return proposal


async def apply(svc: Services, run: RunHandle, ws: Workspace, proposal: PatchProposal) -> list[str]:
    async with svc.recorder.tool_call(
        run,
        "workspace.apply_patch",
        {
            "task_id": proposal.task_id,
            "files": [e.path for e in proposal.edits],
            "operations": [e.operation for e in proposal.edits],
        },
    ) as res:
        check_scope(proposal, svc.settings.max_patch_files)
        applied = svc.workspaces.apply_edits(ws, proposal.edits)
        res["summary"] = f"{len(applied)} files: {', '.join(applied)}"
    return applied


REPRO_SYSTEM = (
    "You are the Code Generation Agent reproducing a reported bug. Write a minimal regression test (as file "
    "edits, tests only) that fails on the current code because of the bug and will pass once it is fixed. "
    "Do not change production code."
)


async def reproduce(
    svc: Services,
    run: RunHandle,
    *,
    request: str,
    ws: Workspace,
    relevant: list[CodeContext],
    files: list[str],
    test_dirs: list[str],
) -> PatchProposal:
    excerpts = "\n\n".join(
        fence(f"ctx-{i}", f"# {c.path}:{c.start_line}\n{c.content}", 6000) for i, c in enumerate(relevant)
    )
    prompt = (
        f"Bug report:\n{fence('bug', request, 6000)}\n\nTest directories: {', '.join(test_dirs) or 'none'}\n\n"
        f"Relevant code:\n{excerpts}"
    )
    proposal = await svc.llm.structured(
        PatchProposal,
        purpose="reproduce",
        system=REPRO_SYSTEM,
        prompt=prompt,
        run=run,
        context={"request": request, "files": files},
    )
    check_scope(proposal, svc.settings.max_patch_files)
    return proposal
