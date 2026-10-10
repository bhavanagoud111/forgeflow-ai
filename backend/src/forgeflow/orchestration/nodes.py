"""Graph nodes. Each node is a thin, typed adapter between graph state and one agent.

Nodes validate what they read from state, call exactly one agent, validate what the
agent returns and write plain data back. Routing decisions live in ``routes`` below and
depend only on state, so transitions are deterministic for a given state.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import Send, interrupt
from sqlalchemy import select, update

from forgeflow.agents import analyst, coder, debugger, planner, pr_agent, reviewer, verifier
from forgeflow.db.models import Approval, Execution, Repository, utcnow
from forgeflow.integrations.github import GitHubNotConfigured
from forgeflow.orchestration.deps import resolve_batches
from forgeflow.orchestration.runtime import Ctx, dump, step
from forgeflow.orchestration.state import ExecutionState, TaskPayload
from forgeflow.repository.indexer import RepositoryIndex, analyze_repository
from forgeflow.schemas import (
    CodeContext,
    ImplementationPlan,
    PatchProposal,
    RepositoryAnalysis,
    ReviewReport,
    TaskSpec,
    TestRun,
    VerificationReport,
)
from forgeflow.workspace.manager import EditError, Workspace

log = logging.getLogger("forgeflow.nodes")

_TEST_PATH = re.compile(r"(^|/)(tests?/|__tests__/|test_[^/]*$|[^/]*_test\.(py|go)$|conftest\.py$)|\.(test|spec)\.")


def _ws(ctx: Ctx, state: ExecutionState | TaskPayload) -> Workspace:
    return ctx.svc.workspaces.get(state["workspace_id"], state["branch"])


async def _index(ctx: Ctx, ws: Workspace) -> RepositoryIndex:
    if ws.id not in ctx.indexes:
        _, idx = await asyncio.to_thread(analyze_repository, ws.path)
        ctx.indexes[ws.id] = idx
    return ctx.indexes[ws.id]


def _plan(state: ExecutionState) -> ImplementationPlan | None:
    return ImplementationPlan.model_validate(state["plan"]) if state.get("plan") else None


# --------------------------------------------------------------------------- preparation


async def prepare_workspace(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "orchestrator", "prepare_workspace", message="Creating isolated workspace") as run:
        async with svc.db.session() as s:
            repo = await s.get(Repository, state["repository_id"])
            assert repo is not None
            provider, full_name, local_path, default_branch = (
                repo.provider,
                repo.full_name,
                repo.local_path,
                repo.default_branch,
            )
        branch = f"forgeflow/{eid.removeprefix('exec_')}"
        base_branch = state["params"].get("base_branch") or default_branch
        async with svc.recorder.tool_call(
            run, "workspace.create", {"repository": full_name, "base": base_branch}
        ) as res:
            if provider == "local":
                assert local_path
                ws = await svc.workspaces.create_from_local(eid, Path(local_path), branch)
                base_sha = ""
            else:
                base_sha = await svc.github.get_branch_sha(full_name, base_branch)
                data = await svc.github.download_tarball(full_name, base_sha)
                ws = await svc.workspaces.create_from_tarball(eid, data, branch)
            res["summary"] = f"{ws.path.name} on {branch}" + (f" from {base_sha[:10]}" if base_sha else "")
    return {
        "workspace_id": ws.id,
        "branch": branch,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "repo_provider": provider,
        "repo_name": full_name,
        "debug_attempts": 0,
        "test_runs": 0,
        "diagnoses": [],
        "applied": [],
    }


async def analyze(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "repository_analyst", "analyze", message="Analysing repository structure") as run:
        ws = _ws(ctx, state)
        analysis, summary, index = await analyst.analyze(svc, run, ws.path, state["repo_name"])
        ctx.indexes[ws.id] = index
        relevant = await analyst.retrieve(svc, run, index, state["request"]) if state.get("request") else []
        async with svc.recorder.tool_call(run, "memory.save", {"repository_id": state["repository_id"]}) as res:
            await svc.memory.save_repository(state["repository_id"], analyst.memory_entries(analysis, summary))
            async with svc.db.session() as s:
                await s.execute(
                    update(Repository)
                    .where(Repository.id == state["repository_id"])
                    .values(analysis={"analysis": dump(analysis), "summary": dump(summary)}, analyzed_at=utcnow())
                )
            res["summary"] = "repository memory updated"
        run.extra.update({"files": analysis.file_count, "frameworks": analysis.frameworks})
    return {"analysis": dump(analysis), "summary": dump(summary), "relevant": [dump(c) for c in relevant]}


# --------------------------------------------------------------------------- planning


async def plan(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "task_planner", "plan", message="Planning tasks") as run:
        async with svc.recorder.tool_call(run, "memory.recall", {"query": state["request"][:200]}) as res:
            history = await svc.memory.recall(state["repository_id"], state["request"])
            res["summary"] = f"{len(history)} related records"
        result = await planner.plan(
            svc,
            run,
            workflow=state["workflow"],
            request=state["request"],
            analysis=RepositoryAnalysis.model_validate(state["analysis"]),
            architecture=state["summary"]["architecture"],
            relevant=[CodeContext.model_validate(c) for c in state.get("relevant", [])],
            history=history,
        )
        run.extra["tasks"] = len(result.tasks)
    await svc.events.emit(
        eid,
        "plan.created",
        f"{len(result.tasks)} tasks planned",
        agent_id="task_planner",
        node="plan",
        data={"plan": dump(result)},
    )
    return {"plan": dump(result)}


async def resolve_dependencies(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    eid = state["execution_id"]
    async with step(ctx, eid, "orchestrator", "resolve_dependencies", message="Resolving task dependencies") as run:
        p = _plan(state)
        assert p is not None
        async with ctx.svc.recorder.tool_call(run, "deps.resolve", {"tasks": len(p.tasks)}) as res:
            batches = resolve_batches(p.tasks, ctx.svc.settings.max_parallel_tasks)
            res["summary"] = " -> ".join("[" + ", ".join(b) + "]" for b in batches)
        run.extra["batches"] = batches
    return {"batches": batches, "batch_index": 0}


def dispatch_batch(state: ExecutionState) -> list[Send] | str:
    """Fan out the current batch to parallel code-generation branches."""
    batches = state.get("batches", [])
    idx = state.get("batch_index", 0)
    if idx >= len(batches):
        return "run_tests"
    p = _plan(state)
    assert p is not None
    by_id = {t.task_id: t for t in p.tasks}
    analysis = state["analysis"]
    files = [m["path"] for m in analysis["modules"]] + analysis["root_files"]
    return [
        Send(
            "generate_task",
            TaskPayload(
                execution_id=state["execution_id"],
                workflow=state["workflow"],
                request=state["request"],
                task=dump(by_id[tid]),
                workspace_id=state["workspace_id"],
                branch=state["branch"],
                files=files,
                conventions=analysis.get("conventions", []),
                relevant=state.get("relevant", []),
            ),
        )
        for tid in batches[idx]
    ]


async def generate_task(payload: TaskPayload, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    task = TaskSpec.model_validate(payload["task"])
    async with step(
        ctx,
        payload["execution_id"],
        "code_generator",
        f"generate:{task.task_id}",
        message=f"Generating changes for {task.task_id}: {task.title}",
    ) as run:
        ws = _ws(ctx, payload)
        index = await _index(ctx, ws)
        relevant = await analyst.retrieve(
            svc, run, index, f"{task.title} {task.description} " + " ".join(task.target_files), k=6
        )
        proposal = await coder.generate(
            svc,
            run,
            workflow=payload["workflow"],
            request=payload["request"],
            task=task,
            ws=ws,
            relevant=relevant,
            files=payload["files"],
            conventions=payload["conventions"],
        )
        run.extra.update({"task_id": task.task_id, "edits": len(proposal.edits)})
    return {"proposals": [dump(proposal)]}


async def apply_batch(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    idx = state["batch_index"]
    batch = state["batches"][idx]
    async with step(ctx, eid, "code_generator", "apply_batch", message=f"Applying batch {idx + 1}") as run:
        ws = _ws(ctx, state)
        # Latest proposal per task in this batch, in deterministic task order.
        latest: dict[str, PatchProposal] = {}
        for raw in state.get("proposals", []):
            pp = PatchProposal.model_validate(raw)
            if pp.task_id in batch:
                latest[pp.task_id] = pp
        applied = list(state.get("applied", []))
        for tid in batch:
            proposal = latest.get(tid)
            if proposal is None or not proposal.edits:
                applied.append(
                    {
                        "task_id": tid,
                        "files": [],
                        "summary": proposal.summary if proposal else "no proposal",
                        "notes": proposal.notes if proposal else [],
                    }
                )
                continue
            if state["workflow"] == "test_generation":
                bad = [e.path for e in proposal.edits if not _TEST_PATH.search(e.path)]
                if bad:
                    raise coder.PatchRejected(f"test generation may only change test files: {bad}")
            try:
                files = await coder.apply(svc, run, ws, proposal)
            except EditError as exc:
                raise EditError(f"{tid}: {exc}") from exc
            applied.append({"task_id": tid, "files": files, "summary": proposal.summary, "notes": proposal.notes})
            await svc.events.emit(
                eid,
                "patch.applied",
                f"{tid}: {len(files)} files changed",
                agent_id="code_generator",
                node="apply_batch",
                data={"task_id": tid, "files": files, "summary": proposal.summary},
            )
    return {"applied": applied, "batch_index": idx + 1}


# --------------------------------------------------------------------------- testing and debugging


async def run_tests(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    if not any(a["files"] for a in state.get("applied", [])) and state["workflow"] != "bug_investigation":
        notes = [n for a in state.get("applied", []) for n in a.get("notes", [])]
        return {"outcome": "failed", "outcome_reason": "No code changes were produced. " + " ".join(notes[:2])}
    attempt = state.get("test_runs", 0) + 1
    async with step(ctx, eid, "verifier", "run_tests", attempt=attempt, message="Running tests in sandbox") as run:
        ws = _ws(ctx, state)
        result = await verifier.run_tests(svc, run, ws, state["analysis"]["verification_profile"])
        run.extra.update({"passed": result.passed, "failed_tests": result.failed_tests[:10]})
    await svc.events.emit(
        eid,
        "test.passed" if result.passed else "test.failed",
        result.summary,
        agent_id="verifier",
        node="run_tests",
        data={"attempt": attempt, "failed_tests": result.failed_tests, "commands": [dump(c) for c in result.commands]},
    )
    return {"test_run": dump(result), "test_runs": attempt}


def debug_limit(state: ExecutionState, max_attempts: int) -> int:
    # The bug workflow's first diagnosis is the investigation itself, not a retry.
    return max_attempts + (1 if state["workflow"] == "bug_investigation" else 0)


async def debug(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    attempt = state.get("debug_attempts", 0) + 1
    test_run = TestRun.model_validate(state["test_run"])
    async with step(
        ctx, eid, "debugger", "debug", attempt=attempt, message=f"Diagnosing failure (attempt {attempt})"
    ) as run:
        ws = _ws(ctx, state)
        changed = [c["path"] for c in await svc.workspaces.changed_files(ws)]
        async with svc.recorder.tool_call(run, "memory.recall", {"kinds": ["failure_pattern", "approved_fix"]}) as res:
            history = await svc.memory.recall(
                state["repository_id"],
                debugger.failure_text(test_run)[-2000:] + " " + state["request"],
                kinds=("failure_pattern", "approved_fix"),
            )
            res["summary"] = f"{len(history)} related records"
        diagnosis = await debugger.diagnose(
            svc,
            run,
            ws=ws,
            test_run=test_run,
            attempt=attempt,
            changed_files=changed,
            related_files=[c["path"] for c in state.get("relevant", [])],
            previous=state.get("diagnoses", []),
            history=history,
        )
        record = {"attempt": attempt, **dump(diagnosis), "applied_files": []}
        if diagnosis.give_up or diagnosis.fix is None or not diagnosis.fix.edits:
            run.extra["gave_up"] = True
            return {
                "debug_attempts": attempt,
                "diagnoses": [*state.get("diagnoses", []), record],
                "outcome": "failed",
                "outcome_reason": f"Debugging agent could not resolve the failure: {diagnosis.root_cause}",
            }
        files = await coder.apply(svc, run, ws, diagnosis.fix)
        record["applied_files"] = files
        await svc.events.emit(
            eid,
            "patch.applied",
            f"Debug fix (attempt {attempt}): {', '.join(files)}",
            agent_id="debugger",
            node="debug",
            data={"files": files, "summary": diagnosis.fix.summary},
        )
    await svc.memory.remember(
        state["repository_id"],
        "failure_pattern",
        f"Test failure: {', '.join(test_run.failed_tests[:3]) or 'verification'}",
        diagnosis.root_cause,
        execution_id=eid,
        tags=test_run.failed_tests[:5],
    )
    return {"debug_attempts": attempt, "diagnoses": [*state.get("diagnoses", []), record]}


# --------------------------------------------------------------------------- bug investigation


async def reproduce(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    analysis = RepositoryAnalysis.model_validate(state["analysis"])
    async with step(ctx, eid, "code_generator", "reproduce", message="Writing a failing regression test") as run:
        ws = _ws(ctx, state)
        proposal = await coder.reproduce(
            svc,
            run,
            request=state["request"],
            ws=ws,
            relevant=[CodeContext.model_validate(c) for c in state.get("relevant", [])],
            files=[m.path for m in analysis.modules] + analysis.root_files,
            test_dirs=analysis.test_dirs,
        )
        bad = [e.path for e in proposal.edits if not _TEST_PATH.search(e.path)]
        if bad:
            raise coder.PatchRejected(f"reproduction may only add tests: {bad}")
        files = await coder.apply(svc, run, ws, proposal) if proposal.edits else []
    plan_ = ImplementationPlan(
        summary=f"Investigate and fix: {state['request'][:300]}",
        tasks=[
            TaskSpec(
                task_id="TASK-001",
                title="Reproduce the reported bug",
                kind="tests",
                description="Add a regression test that fails on the current code.",
                acceptance_criteria=["Regression test reproduces the bug"],
                target_files=files,
            ),
            TaskSpec(
                task_id="TASK-002",
                title="Fix the root cause",
                kind="fix",
                dependencies=["TASK-001"],
                description="Correct the defect identified by the debugging agent.",
                acceptance_criteria=["Regression test passes", "Existing tests pass"],
            ),
        ],
    )
    applied = [{"task_id": "TASK-001", "files": files, "summary": proposal.summary, "notes": proposal.notes}]
    if not files:
        return {
            "plan": dump(plan_),
            "applied": applied,
            "outcome": "failed",
            "outcome_reason": "Could not write a reproduction test. " + " ".join(proposal.notes),
        }
    return {"plan": dump(plan_), "applied": applied, "reproduction": {"files": files, "summary": proposal.summary}}


def after_reproduce_tests(state: ExecutionState) -> str:
    if state.get("outcome"):
        return "report"
    if TestRun.model_validate(state["test_run"]).passed:
        return "not_reproduced"
    return "debug"


async def not_reproduced(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    return {
        "outcome": "failed",
        "outcome_reason": "The regression test passed on unmodified code, so the bug was not reproduced.",
    }


# --------------------------------------------------------------------------- review, verification, delivery


async def review(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "code_reviewer", "review", message="Reviewing the change") as run:
        if state["workflow"] == "code_review":
            diff, changed = state["diff"], state["changed"]
        else:
            ws = _ws(ctx, state)
            diff = await svc.workspaces.diff(ws)
            changed = await svc.workspaces.changed_files(ws)
        p = _plan(state)
        report = await reviewer.review(
            svc, run, diff=diff, changed=changed, request=state["request"], plan_summary=p.summary if p else ""
        )
        run.extra.update({"findings": len(report.findings), "blocking": report.blocking})
    await svc.events.emit(
        eid,
        "review.completed",
        f"{len(report.findings)} findings" + (" (blocking)" if report.blocking else ""),
        agent_id="code_reviewer",
        node="review",
        data={"review": dump(report)},
    )
    out: dict[str, Any] = {"review": dump(report), "diff": diff, "changed": changed}
    if report.blocking and state["workflow"] != "code_review":
        out.update(outcome="blocked", outcome_reason="Critical review findings block automated progression.")
    return out


async def verify(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    p = _plan(state)
    assert p is not None
    async with step(ctx, eid, "verifier", "verify", message="Verifying acceptance criteria") as run:
        ws = _ws(ctx, state)
        report = await verifier.verify(
            svc,
            run,
            ws=ws,
            tasks=p.tasks,
            diff=state["diff"],
            changed_files=[c["path"] for c in state["changed"]],
            test_profile=state["analysis"]["verification_profile"],
            lint_profile=state["analysis"]["lint_profile"],
        )
        run.extra["complete"] = report.complete
    await svc.events.emit(
        eid,
        "verification.completed",
        report.summary,
        agent_id="verifier",
        node="verify",
        data={"verification": dump(report)},
    )
    out: dict[str, Any] = {"verification": dump(report)}
    if not report.complete:
        out.update(outcome="failed", outcome_reason=report.summary)
    return out


async def draft_pr(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "pull_request", "draft_pr", message="Preparing pull request") as run:
        p = _plan(state)
        narrative = await pr_agent.draft(svc, run, request=state["request"], plan=p, diff=state["diff"])
        issue = state["params"].get("issue")
        body = pr_agent.build_body(
            narrative,
            plan=p,
            verification=VerificationReport.model_validate(state["verification"]),
            review=ReviewReport.model_validate(state["review"]),
            changed=state["changed"],
            execution_id=eid,
            simulated=svc.llm.simulated,
            issue=f"#{issue}" if issue else None,
        )
    return {
        "pr_draft": {"title": narrative.title, "body": body, "branch": state["branch"], "base": state["base_branch"]}
    }


async def request_approval(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    """Human-in-the-loop gate. Re-entered on resume, so everything before interrupt() is idempotent."""
    svc = runtime.context.svc
    eid = state["execution_id"]
    publish = state["repo_provider"] == "github"
    permissions = (
        [
            f"contents:write on {state['repo_name']} (branch {state['branch']} only)",
            f"pull_requests:write on {state['repo_name']} (draft pull request into {state['base_branch']})",
        ]
        if publish
        else ["none (local repository: the pull request is prepared, not published)"]
    )
    async with svc.db.session() as s:
        approval = await s.scalar(
            select(Approval).where(Approval.execution_id == eid, Approval.action == "create_pull_request")
        )
        created = approval is None
        if approval is None:
            approval = Approval(
                execution_id=eid,
                action="create_pull_request",
                title=state["pr_draft"]["title"],
                details={
                    "repository": state["repo_name"],
                    "branch": state["branch"],
                    "base": state["base_branch"],
                    "files": state["changed"],
                    "verification": state["verification"]["summary"],
                    "review_summary": state["review"]["summary"],
                    "publish": publish,
                },
                requested_permissions=permissions,
            )
            s.add(approval)
            await s.flush()
        approval_id = approval.id
        await s.execute(
            update(Execution)
            .where(Execution.id == eid)
            .values(status="awaiting_approval", current_node="request_approval")
        )
    if created:
        await svc.events.emit(
            eid,
            "approval.required",
            f"Approval required: {state['pr_draft']['title']}",
            agent_id="pull_request",
            node="request_approval",
            data={"approval_id": approval_id, "permissions": permissions},
        )
    decision = interrupt({"approval_id": approval_id, "action": "create_pull_request"})
    return {"approval": {"id": approval_id, **decision}}


def after_approval(state: ExecutionState) -> str:
    return "create_pr" if state["approval"].get("decision") == "approved" else "rejected"


async def rejected(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    a = state["approval"]
    return {"outcome": "rejected", "outcome_reason": f"Rejected by {a.get('by')}: {a.get('comment') or 'no comment'}"}


async def create_pr(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    async with step(ctx, eid, "pull_request", "create_pr", message="Creating pull request") as run:
        ws = _ws(ctx, state)
        draft = state["pr_draft"]
        if state["repo_provider"] == "github":
            pr = await pr_agent.publish_github(
                svc,
                run,
                ws=ws,
                repo=state["repo_name"],
                base_branch=draft["base"],
                base_sha=state["base_sha"],
                title=draft["title"],
                body=draft["body"],
            )
            pr["published"] = True
            message = f"Pull request opened: {pr['url']}"
        else:
            commit = await svc.workspaces.commit(ws, draft["title"])
            pr = {
                "published": False,
                "branch": ws.branch,
                "commit": commit,
                "url": None,
                "note": "Local repository: pull request prepared in the workspace, not published.",
            }
            message = "Pull request prepared locally (not published)."
    await svc.events.emit(eid, "pr.created", message, agent_id="pull_request", node="create_pr", data=pr)
    return {"pr": pr, "outcome": "succeeded", "outcome_reason": message}


# --------------------------------------------------------------------------- code review workflow


async def load_diff(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    params = state["params"]
    async with step(ctx, eid, "orchestrator", "load_diff", message="Loading change for review") as run:
        async with svc.db.session() as s:
            repo = await s.get(Repository, state["repository_id"])
            assert repo is not None
            provider, name = repo.provider, repo.full_name
        if params.get("pr_number"):
            if provider != "github":
                raise ValueError("pr_number requires a GitHub repository")
            async with svc.recorder.tool_call(
                run, "github.get_pull", {"repo": name, "number": params["pr_number"]}
            ) as res:
                try:
                    diff = await svc.github.get_pull_diff(name, int(params["pr_number"]))
                except GitHubNotConfigured as exc:
                    raise ValueError(str(exc)) from exc
                res["summary"] = f"{len(diff.splitlines())} diff lines"
        elif params.get("diff"):
            diff = str(params["diff"])
        else:
            raise ValueError("code_review needs params.pr_number (GitHub) or params.diff")
    files = reviewer.parse_diff(diff)
    changed = []
    for path in files:
        status = "modified"
        if re.search(rf"--- /dev/null\n\+\+\+ b/{re.escape(path)}\n", diff):
            status = "added"
        elif re.search(rf"--- a/{re.escape(path)}\n\+\+\+ /dev/null\n", diff):
            status = "deleted"
        changed.append({"path": path, "status": status})
    return {"diff": diff, "changed": changed, "repo_name": name, "repo_provider": provider}


async def review_done(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    r = ReviewReport.model_validate(state["review"])
    counts: dict[str, int] = {}
    for f in r.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return {
        "outcome": "succeeded",
        "outcome_reason": f"Review complete: {', '.join(f'{v} {k}' for k, v in counts.items()) or 'no findings'}.",
    }


async def onboarding_done(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    return {"outcome": "succeeded", "outcome_reason": "Repository analysed and repository memory updated."}


# --------------------------------------------------------------------------- report


async def report(state: ExecutionState, runtime: Runtime[Ctx]) -> dict[str, Any]:
    ctx = runtime.context
    svc = ctx.svc
    eid = state["execution_id"]
    outcome = state.get("outcome") or "failed"
    reason = state.get("outcome_reason") or "Workflow ended without an outcome."
    async with step(ctx, eid, "orchestrator", "report", message="Compiling execution report"):
        p = state.get("plan")
        test_run = state.get("test_run")
        result = {
            "outcome": outcome,
            "reason": reason,
            "workflow": state["workflow"],
            "repository": state.get("repo_name"),
            "branch": state.get("branch"),
            "plan": p,
            "batches": state.get("batches"),
            "applied": state.get("applied", []),
            "changed": state.get("changed", []),
            "diff": (state.get("diff") or "")[:400_000],
            "test_run": test_run,
            "test_runs": state.get("test_runs", 0),
            "debug_attempts": state.get("debug_attempts", 0),
            "diagnoses": state.get("diagnoses", []),
            "review": state.get("review"),
            "verification": state.get("verification"),
            "pr_draft": state.get("pr_draft"),
            "pr": state.get("pr"),
            "approval": state.get("approval"),
            "analysis_summary": state.get("summary"),
            "simulated": svc.llm.simulated,
        }
        if not result["diff"] and state.get("workspace_id") and state["workflow"] != "code_review":
            try:
                ws = _ws(ctx, state)
                result["diff"] = (await svc.workspaces.diff(ws))[:400_000]
                result["changed"] = await svc.workspaces.changed_files(ws)
            except Exception:  # workspace may be gone; the report is still useful
                log.debug("diff unavailable for %s", eid, exc_info=True)
        changed_files: list[dict[str, str]] = result["changed"] or []  # type: ignore[assignment]
        repo_id = state["repository_id"]
        title = state["request"][:200] or state["workflow"]
        if state["workflow"] == "bug_investigation" and state.get("diagnoses"):
            await svc.memory.remember(
                repo_id, "investigation", title, state["diagnoses"][-1]["root_cause"], execution_id=eid
            )
        if outcome == "succeeded" and state.get("pr"):
            await svc.memory.remember(
                repo_id,
                "approved_fix",
                title,
                f"{reason}\nFiles: {', '.join(c['path'] for c in changed_files)}",
                execution_id=eid,
            )
        elif outcome in ("rejected", "blocked"):
            await svc.memory.remember(repo_id, "decision", f"{outcome}: {title}", reason, execution_id=eid)
    # Artifact retention: the diff, test output and report are kept in the database. The workspace is
    # kept only when it holds a locally prepared (unpublished) pull request; the retention job purges it.
    pr = state.get("pr") or {}
    keep_workspace = outcome == "succeeded" and bool(pr) and not pr.get("published")
    if state.get("workspace_id") and not keep_workspace:
        svc.workspaces.remove(state["workspace_id"])
    return {"report": result, "outcome": outcome, "outcome_reason": reason}
