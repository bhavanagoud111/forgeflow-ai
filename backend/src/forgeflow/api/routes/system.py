from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, text

from forgeflow import __version__
from forgeflow.agents.base import AGENTS
from forgeflow.api.deps import Admin, ContainerDep, PageDep, Viewer
from forgeflow.api.schemas import AgentOut, AgentRunOut, Me, ToolCallOut, WorkflowOut
from forgeflow.db.models import AgentRun, Approval, AuditLog, Execution, Repository, ToolCall, utcnow
from forgeflow.orchestration.workflows import describe
from forgeflow.schemas import Workflow

router = APIRouter(prefix="/api", tags=["system"])

WORKFLOW_INFO = {
    Workflow.feature: (
        "Feature implementation",
        "Plan, implement in parallel, test, debug, review, verify and open a PR.",
    ),
    Workflow.bug_investigation: ("Bug investigation", "Reproduce with a failing test, diagnose, fix and verify."),
    Workflow.code_review: ("Automated code review", "Static and model review of a pull request or diff."),
    Workflow.repo_onboarding: ("Repository onboarding", "Analyse structure and store repository memory."),
    Workflow.test_generation: ("Test generation", "Plan and add tests only, verified in the sandbox."),
}


@router.get("/health", summary="Liveness and dependency status")
async def health(c: ContainerDep) -> dict[str, Any]:
    db_ok = True
    try:
        async with c.services.db.session() as s:
            await s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    st = c.services.settings
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": db_ok,
        "llm_provider": st.llm_provider,
        "simulated_llm": c.services.llm.simulated,
        "sandbox": c.services.sandbox.name,
        "github": st.github_configured,
        "slack": st.slack_configured,
    }


@router.get("/me", response_model=Me, summary="Current principal")
async def me(p: Viewer) -> Me:
    return Me(id=p.id, name=p.name, role=p.role.name)


@router.get("/workflows", response_model=list[WorkflowOut], summary="Workflow definitions and graphs")
async def workflows(_: Viewer) -> list[WorkflowOut]:
    return [WorkflowOut(id=w.value, title=t, description=d, graph=describe(w)) for w, (t, d) in WORKFLOW_INFO.items()]


@router.get("/agents", response_model=list[AgentOut], summary="Agents with live state and recent activity")
async def agents(c: ContainerDep, _: Viewer) -> list[AgentOut]:
    out = []
    async with c.services.db.session() as s:
        for info in AGENTS.values():
            running = list(
                await s.scalars(select(AgentRun).where(AgentRun.agent_id == info.id, AgentRun.status == "running"))
            )
            recent = list(
                await s.scalars(
                    select(AgentRun).where(AgentRun.agent_id == info.id).order_by(AgentRun.started_at.desc()).limit(10)
                )
            )
            stats = (
                await s.execute(
                    select(func.count(AgentRun.id), func.avg(AgentRun.duration_ms)).where(AgentRun.agent_id == info.id)
                )
            ).one()
            failures = (
                await s.scalar(
                    select(func.count(AgentRun.id)).where(AgentRun.agent_id == info.id, AgentRun.status == "failed")
                )
                or 0
            )
            tools = list(
                await s.scalars(
                    select(ToolCall).where(ToolCall.agent_id == info.id).order_by(ToolCall.started_at.desc()).limit(8)
                )
            )
            last = recent[0] if recent else None
            state = "active" if running else ("error" if last and last.status == "failed" else "idle")
            out.append(
                AgentOut(
                    id=info.id,
                    name=info.name,
                    description=info.description,
                    responsibilities=info.responsibilities,
                    tools=info.tools,
                    uses_llm=info.uses_llm,
                    state=state,
                    active_executions=sorted({r.execution_id for r in running}),
                    recent_nodes=[r.node for r in recent[:5]],
                    last_run=AgentRunOut.model_validate(last) if last else None,
                    runs_total=int(stats[0] or 0),
                    failures_total=int(failures),
                    avg_duration_ms=int(stats[1]) if stats[1] is not None else None,
                    recent_tools=[ToolCallOut.model_validate(t) for t in tools],
                )
            )
    return out


@router.get("/metrics", summary="Aggregate execution metrics")
async def metrics(c: ContainerDep, _: Viewer) -> dict[str, Any]:
    async with c.services.db.session() as s:
        by_status = dict((await s.execute(select(Execution.status, func.count()).group_by(Execution.status))).all())
        by_workflow = dict(
            (await s.execute(select(Execution.workflow, func.count()).group_by(Execution.workflow))).all()
        )
        finished = list(
            await s.execute(
                select(Execution.started_at, Execution.finished_at).where(
                    Execution.finished_at.is_not(None), Execution.started_at.is_not(None)
                )
            )
        )
        pending = await s.scalar(select(func.count(Approval.id)).where(Approval.status == "pending")) or 0
        repos = await s.scalar(select(func.count(Repository.id))) or 0
        usage = (
            await s.execute(
                select(
                    func.sum(AgentRun.input_tokens),
                    func.sum(AgentRun.output_tokens),
                    func.sum(AgentRun.cost_usd),
                    func.count(AgentRun.id),
                )
            )
        ).one()
        per_agent = (
            await s.execute(
                select(AgentRun.agent_id, func.count(), func.avg(AgentRun.duration_ms)).group_by(AgentRun.agent_id)
            )
        ).all()
        tool_errors = await s.scalar(select(func.count(ToolCall.id)).where(ToolCall.status == "failed")) or 0
        since = utcnow() - timedelta(days=14)
        recent = list(
            await s.execute(select(Execution.created_at, Execution.status).where(Execution.created_at >= since))
        )
    durations = [(f - st).total_seconds() * 1000 for st, f in finished if st and f]
    daily: dict[str, dict[str, int]] = {}
    for created, status in recent:
        day = created.date().isoformat()
        bucket = daily.setdefault(day, {"succeeded": 0, "failed": 0, "other": 0})
        key = status if status in ("succeeded", "failed") else "other"
        bucket[key] += 1
    active = sum(by_status.get(k, 0) for k in ("queued", "running", "resuming", "awaiting_approval"))
    return {
        "executions": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "by_workflow": by_workflow,
            "active": active,
            "completed": by_status.get("succeeded", 0),
            "failed": by_status.get("failed", 0) + by_status.get("blocked", 0),
        },
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
        "pending_approvals": pending,
        "repositories": repos,
        "usage": {
            "input_tokens": int(usage[0] or 0),
            "output_tokens": int(usage[1] or 0),
            "cost_usd": round(float(usage[2] or 0), 6),
            "agent_runs": int(usage[3] or 0),
            "tool_errors": tool_errors,
        },
        "agents": [
            {"agent_id": a, "runs": n, "avg_duration_ms": int(d) if d is not None else None} for a, n, d in per_agent
        ],
        "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
    }


@router.get("/settings", summary="Effective configuration (secrets omitted)")
async def settings_view(c: ContainerDep, _: Viewer) -> dict[str, Any]:
    st = c.services.settings
    return {
        "llm": {
            "provider": st.llm_provider,
            "model": st.llm_model if st.llm_provider != "demo" else "demo",
            "simulated": c.services.llm.simulated,
            "api_key_configured": st.llm_api_key is not None,
        },
        "github": {
            "configured": st.github_configured,
            "auth": "app" if st.github_app_id else "token" if st.github_token else None,
            "api_url": st.github_api_url,
        },
        "slack": {
            "configured": st.slack_configured,
            "bot_token_configured": st.slack_bot_token is not None,
            "authorized_users": len(st.slack_user_roles),
        },
        "limits": {
            "execution_timeout_seconds": st.execution_timeout_seconds,
            "node_timeout_seconds": st.node_timeout_seconds,
            "max_debug_attempts": st.max_debug_attempts,
            "max_parallel_tasks": st.max_parallel_tasks,
            "max_patch_files": st.max_patch_files,
            "rate_limit_per_minute": st.rate_limit_per_minute,
        },
        "sandbox": {
            "mode": st.sandbox_mode,
            "image": st.sandbox_image,
            "cpus": st.sandbox_cpus,
            "memory_mb": st.sandbox_memory_mb,
            "pids_limit": st.sandbox_pids_limit,
            "command_timeout_seconds": st.sandbox_command_timeout_seconds,
            "allow_dependency_install": st.allow_dependency_install,
            "allow_unsafe_local_sandbox": st.allow_unsafe_local_sandbox,
        },
        "retention": {
            "workspace_hours": st.workspace_retention_hours,
            "event_days": st.event_retention_days,
            "history_days": st.history_retention_days,
        },
        "observability": {"otlp_endpoint_configured": bool(st.otel_exporter_otlp_endpoint)},
    }


@router.get("/audit", summary="Audit log (admin)")
async def audit_log(c: ContainerDep, _: Admin, page: PageDep) -> dict[str, Any]:
    async with c.services.db.session() as s:
        total = await s.scalar(select(func.count(AuditLog.id))) or 0
        rows = list(
            await s.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(page.limit).offset(page.offset))
        )
    return {
        "items": [
            {"actor": r.actor, "action": r.action, "target": r.target, "details": r.details, "created_at": r.created_at}
            for r in rows
        ],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }
