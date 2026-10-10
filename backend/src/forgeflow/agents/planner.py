"""Task Planning Agent."""

from __future__ import annotations

import json
from typing import Any

from forgeflow.agents.base import Services
from forgeflow.orchestration.deps import resolve_batches
from forgeflow.schemas import CodeContext, ImplementationPlan, RepositoryAnalysis
from forgeflow.security.untrusted import fence
from forgeflow.telemetry import RunHandle

SYSTEM = (
    "You are the Task Planning Agent. Produce an implementation plan for the request as a small set of "
    "tasks (1-8) with ids TASK-001, TASK-002, ... Each task must have concrete acceptance criteria, the "
    "repository-relative files it will touch, and dependencies only on earlier tasks that it truly needs. "
    "Prefer independent tasks so they can run in parallel. Include test work. Keep scope tight: do not plan "
    "unrelated refactors, CI changes or dependency upgrades."
)

TEST_SYSTEM = SYSTEM + " This is a test-generation request: plan only test additions, no production changes."


async def plan(
    svc: Services,
    run: RunHandle,
    *,
    workflow: str,
    request: str,
    analysis: RepositoryAnalysis,
    architecture: str,
    relevant: list[CodeContext],
    history: list[dict[str, Any]],
) -> ImplementationPlan:
    excerpts = "\n\n".join(
        fence(f"file-{i}", f"# {c.path} (lines {c.start_line}-{c.end_line})\n{c.content}", 4000)
        for i, c in enumerate(relevant)
    )
    past = "\n".join(f"- [{h['kind']}] {h['title']}: {h['content'][:300]}" for h in history) or "none"
    prompt = (
        f"Request:\n{fence('request', request, 8000)}\n\n"
        f"Architecture summary:\n{architecture}\n\n"
        f"Frameworks: {', '.join(analysis.frameworks)}; tests in: {', '.join(analysis.test_dirs) or 'none'}\n"
        f"Repository files (partial):\n{json.dumps([m.path for m in analysis.modules][:200])}\n\n"
        f"Relevant code excerpts:\n{excerpts}\n\nRelated history:\n{past}"
    )
    result = await svc.llm.structured(
        ImplementationPlan,
        purpose="plan",
        system=TEST_SYSTEM if workflow == "test_generation" else SYSTEM,
        prompt=prompt,
        run=run,
        context={
            "workflow": workflow,
            "request": request,
            "files": [m.path for m in analysis.modules] + analysis.root_files,
            "relevant": [c.model_dump() for c in relevant],
        },
    )
    # Raises on cycles; the plan is rejected rather than executed out of order.
    resolve_batches(result.tasks, svc.settings.max_parallel_tasks)
    return result
