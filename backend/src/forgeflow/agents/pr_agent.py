"""Pull Request Agent."""

from __future__ import annotations

from typing import Any

from forgeflow.agents.base import Services
from forgeflow.integrations.github import FileChange
from forgeflow.schemas import ImplementationPlan, PRNarrative, ReviewReport, VerificationReport
from forgeflow.security.untrusted import fence
from forgeflow.telemetry import RunHandle
from forgeflow.workspace.manager import Workspace

SYSTEM = (
    "You are the Pull Request Agent. Write a concise pull request title (imperative mood, under 72 "
    "characters) and an overview of the change for reviewers. Describe only what the diff does."
)


def build_body(
    narrative: PRNarrative,
    *,
    plan: ImplementationPlan | None,
    verification: VerificationReport,
    review: ReviewReport,
    changed: list[dict[str, str]],
    execution_id: str,
    simulated: bool,
    issue: str | None = None,
) -> str:
    lines = [narrative.overview.strip(), ""]
    if issue:
        lines += [f"Refs {issue}", ""]
    if narrative.notable_changes:
        lines += ["## Changes", *[f"- {c}" for c in narrative.notable_changes], ""]
    lines += ["## Files", *[f"- `{c['path']}` ({c['status']})" for c in changed], ""]
    lines += ["## Verification", f"{verification.summary}", ""]
    for c in verification.commands:
        lines.append(f"- `{' '.join(c.argv)}` -> exit {c.exit_code} ({c.duration_ms} ms, {c.sandbox} sandbox)")
    if verification.criteria:
        lines += ["", "| Task | Criterion | Met |", "| --- | --- | --- |"]
        lines += [f"| {c.task_id} | {c.criterion} | {'yes' if c.met else 'no'} |" for c in verification.criteria]
    notable = [f for f in review.findings if f.severity in ("medium", "high", "critical")]
    lines += ["", "## Review", review.summary]
    lines += [f"- **{f.severity}** {f.title}" + (f" (`{f.file}`)" if f.file else "") for f in notable]
    limits = list(plan.risks) if plan else []
    if simulated:
        limits.append("Generated with the deterministic demo provider (scripted model output).")
    if limits:
        lines += ["", "## Known limitations", *[f"- {r}" for r in limits]]
    lines += [
        "",
        f"<sub>Prepared by ForgeFlow AI, execution `{execution_id}`. Human approval was recorded "
        "before this pull request was opened.</sub>",
    ]
    return "\n".join(lines)


async def draft(
    svc: Services, run: RunHandle, *, request: str, plan: ImplementationPlan | None, diff: str
) -> PRNarrative:
    return await svc.llm.structured(
        PRNarrative,
        purpose="pr",
        system=SYSTEM,
        prompt=f"Request:\n{fence('request', request, 4000)}\n\nDiff:\n{fence('diff', diff, 60_000)}",
        run=run,
        context={"request": request, "plan": plan.model_dump() if plan else None},
    )


async def publish_github(
    svc: Services, run: RunHandle, *, ws: Workspace, repo: str, base_branch: str, base_sha: str, title: str, body: str
) -> dict[str, Any]:
    changed = await svc.workspaces.changed_files(ws)
    changes = [
        FileChange(
            path=c["path"], content=None if c["status"] == "deleted" else svc.workspaces.read_file(ws, c["path"])
        )
        for c in changed
    ]
    unreadable = [
        c.path for c, meta in zip(changes, changed, strict=True) if c.content is None and meta["status"] != "deleted"
    ]
    if unreadable:
        raise RuntimeError(f"cannot publish binary or oversized files: {unreadable}")
    async with svc.recorder.tool_call(
        run, "github.push_branch", {"repo": repo, "branch": ws.branch, "files": len(changes)}
    ) as res:
        sha = await svc.github.push_branch(repo, ws.branch, base_sha, title, changes)
        res["summary"] = f"{ws.branch} @ {sha[:10]}"
    async with svc.recorder.tool_call(
        run, "github.create_pull", {"repo": repo, "head": ws.branch, "base": base_branch}
    ) as res:
        pr = await svc.github.create_pull(repo, head=ws.branch, base=base_branch, title=title, body=body)
        res["summary"] = pr.get("html_url", "")
    return {"url": pr.get("html_url"), "number": pr.get("number"), "branch": ws.branch, "commit": sha}
