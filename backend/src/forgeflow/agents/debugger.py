"""Debugging Agent."""

from __future__ import annotations

import re
from typing import Any

from forgeflow.agents.base import Services
from forgeflow.agents.coder import check_scope
from forgeflow.schemas import Diagnosis, TestRun
from forgeflow.security.untrusted import fence
from forgeflow.telemetry import RunHandle
from forgeflow.workspace.manager import EditError, Workspace

SYSTEM = (
    "You are the Debugging Agent. Analyse the failing verification output, identify the most likely root "
    "cause and propose the smallest corrective patch. Prefer fixing production code over weakening tests; "
    "only change a test if it is demonstrably wrong. If you cannot identify a cause with reasonable "
    "confidence, set give_up=true and explain what is missing. Do not repeat a fix that already failed."
)

_TRACE_PATH = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|go)):\d+")


def failure_text(test_run: TestRun, limit: int = 12_000) -> str:
    parts = []
    for c in test_run.commands:
        if c.exit_code != 0 or c.timed_out:
            parts.append(
                f"$ {' '.join(c.argv)}  (exit {c.exit_code}{', timed out' if c.timed_out else ''})\n"
                f"{c.stdout[-limit:]}\n{c.stderr[-limit // 2 :]}"
            )
    return "\n\n".join(parts)[-limit:]


async def diagnose(
    svc: Services,
    run: RunHandle,
    *,
    ws: Workspace,
    test_run: TestRun,
    attempt: int,
    changed_files: list[str],
    related_files: list[str],
    previous: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> Diagnosis:
    output = failure_text(test_run)
    mentioned = {m.group(1).lstrip("./") for m in _TRACE_PATH.finditer(output)}
    candidates = [
        p
        for p in dict.fromkeys([*changed_files, *sorted(mentioned), *related_files])
        if not p.startswith(("/", "usr/", "lib/"))
    ][:16]
    files: dict[str, str] = {}
    async with svc.recorder.tool_call(run, "workspace.read", {"files": candidates}) as res:
        for p in candidates:
            try:
                content = svc.workspaces.read_file(ws, p)
            except EditError:
                continue
            if content is not None:
                files[p] = content
        res["summary"] = f"read {len(files)} files"
    prior = "\n".join(f"- attempt {p['attempt']}: {p['root_cause'][:300]}" for p in previous) or "none"
    known = "\n".join(f"- {h['title']}: {h['content'][:300]}" for h in history) or "none"
    prompt = (
        f"Attempt {attempt}. Failing output:\n{fence('test-output', output, 12_000)}\n\n"
        f"Previous attempts:\n{prior}\n\nKnown failure patterns in this repository:\n{known}\n\n"
        + "\n\n".join(fence(f"file-{i}", f"# {p}\n{c}", 20_000) for i, (p, c) in enumerate(files.items()))
    )
    diagnosis = await svc.llm.structured(
        Diagnosis,
        purpose="diagnose",
        system=SYSTEM,
        prompt=prompt,
        run=run,
        context={"test_output": output, "attempt": attempt, "workspace_files": files},
    )
    if diagnosis.fix is not None:
        check_scope(diagnosis.fix, svc.settings.max_patch_files)
    return diagnosis
