"""Verification Agent: runs allowlisted checks in the sandbox and evaluates acceptance criteria."""

from __future__ import annotations

import re

from forgeflow.agents.base import Services
from forgeflow.schemas import CommandResult, CriteriaAssessment, TaskSpec, TestRun, VerificationReport
from forgeflow.security.untrusted import fence
from forgeflow.telemetry import RunHandle
from forgeflow.workspace.manager import Workspace

CRITERIA_SYSTEM = (
    "You are the Verification Agent. For each acceptance criterion decide whether the diff and the actual "
    "test results demonstrate it is met. Mark a criterion met only with concrete evidence from the diff or "
    "test output. Test results given to you are real; do not assume tests that were not run."
)

_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)


async def run_commands(svc: Services, run: RunHandle, ws: Workspace, profile: list[list[str]]) -> list[CommandResult]:
    results = []
    for argv in profile:
        async with svc.recorder.tool_call(run, "sandbox.run", {"argv": argv, "sandbox": svc.sandbox.name}) as res:
            result = await svc.sandbox.run(ws.path, argv, svc.settings.sandbox_command_timeout_seconds)
            res["summary"] = f"exit {result.exit_code} in {result.duration_ms} ms" + (
                " (timed out)" if result.timed_out else ""
            )
        results.append(result)
    return results


async def run_tests(svc: Services, run: RunHandle, ws: Workspace, profile: list[list[str]]) -> TestRun:
    if not profile:
        return TestRun(passed=False, commands=[], summary="No test command detected for this repository.")
    commands = await run_commands(svc, run, ws, profile)
    passed = all(c.exit_code == 0 and not c.timed_out for c in commands)
    failed = sorted({m.group(1) for c in commands for m in _FAILED.finditer(c.stdout)})
    tail = [line for c in commands for line in c.stdout.strip().splitlines()[-1:]]
    summary = ("All checks passed. " if passed else "Checks failed. ") + " | ".join(tail)
    return TestRun(passed=passed, commands=commands, summary=summary[:2000], failed_tests=failed[:50])


async def verify(
    svc: Services,
    run: RunHandle,
    *,
    ws: Workspace,
    tasks: list[TaskSpec],
    diff: str,
    changed_files: list[str],
    test_profile: list[list[str]],
    lint_profile: list[list[str]],
) -> VerificationReport:
    tests = await run_tests(svc, run, ws, test_profile)
    lint_cmds = await run_commands(svc, run, ws, lint_profile) if lint_profile else []
    lint_passed = all(c.exit_code == 0 for c in lint_cmds) if lint_cmds else None
    assessment = await svc.llm.structured(
        CriteriaAssessment,
        purpose="criteria",
        system=CRITERIA_SYSTEM,
        prompt=(
            f"Tasks:\n{[t.model_dump() for t in tasks]}\n\nTest summary: {tests.summary}\n"
            f"Lint passed: {lint_passed}\n\nDiff:\n{fence('diff', diff, 60_000)}"
        ),
        run=run,
        context={
            "tasks": [t.model_dump() for t in tasks],
            "tests_passed": tests.passed,
            "changed_files": changed_files,
        },
    )
    expected = {(t.task_id, c) for t in tasks for c in t.acceptance_criteria}
    checks = [c for c in assessment.checks if (c.task_id, c.criterion) in expected]
    covered = {(c.task_id, c.criterion) for c in checks}
    criteria_ok = covered == expected and all(c.met for c in checks)
    complete = tests.passed and lint_passed is not False and criteria_ok and bool(changed_files)
    reasons = []
    if not tests.passed:
        reasons.append("tests failing")
    if lint_passed is False:
        reasons.append("lint/compile checks failing")
    if not criteria_ok:
        reasons.append(f"{sum(1 for c in checks if not c.met) + len(expected - covered)} acceptance criteria unmet")
    if not changed_files:
        reasons.append("no changes")
    return VerificationReport(
        complete=complete,
        tests_passed=tests.passed,
        lint_passed=lint_passed,
        criteria=checks,
        commands=tests.commands + lint_cmds,
        summary="Verified: tests pass and all acceptance criteria are met."
        if complete
        else "Not verified: " + ", ".join(reasons) + ".",
    )
