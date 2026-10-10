"""Deterministic offline provider.

The demo provider lets ForgeFlow run end to end without paid model APIs. It is honest
about what it is: every response is either derived mechanically from real analysis
data, or (for code changes) taken from scripted scenarios written for the bundled
sample repository. Agents mark outputs from this provider as simulated, and requests
it has no script for fail with an explicit message instead of producing fake code.

Everything downstream of the provider is real: patches are applied to an isolated
workspace, tests are executed, failures are captured and fed back to the debugger.
"""

from __future__ import annotations

import re
from typing import Any

from forgeflow.demo import taskboard_files as tb
from forgeflow.llm.base import LLMError, T
from forgeflow.schemas import (
    CriteriaAssessment,
    CriterionCheck,
    Diagnosis,
    FileEdit,
    ImplementationPlan,
    PatchProposal,
    PRNarrative,
    RepositorySummary,
    ReviewFinding,
    ReviewReport,
    TaskSpec,
)
from forgeflow.telemetry import RunHandle


def detect_scenario(workflow: str, request: str, files: list[str]) -> str | None:
    if "taskboard/main.py" not in files or "taskboard/store.py" not in files:
        return None
    text = request.lower()
    if workflow == "feature" and re.search(r"\b(jwt|auth\w*|token)\b", text):
        return "taskboard_jwt"
    if workflow == "bug_investigation" and re.search(r"complet|reopen|patch", text):
        return "taskboard_reopen"
    if workflow == "test_generation":
        return "taskboard_store_tests"
    return None


class DemoLLM:
    provider = "demo"
    model = "demo"
    simulated = True

    async def structured(
        self,
        schema: type[T],
        *,
        purpose: str,
        system: str,
        prompt: str,
        run: RunHandle,
        context: dict[str, Any] | None = None,
    ) -> T:
        ctx = context or {}
        handler = getattr(self, f"_{purpose}", None)
        if handler is None:
            raise LLMError(f"demo provider has no handler for '{purpose}'")
        # Usage is recorded as zero tokens so cost dashboards stay truthful.
        run.add_usage(self.provider, self.model, 0, 0)
        run.extra["simulated"] = True
        result = handler(ctx)
        if not isinstance(result, schema):
            result = schema.model_validate(result.model_dump())
        return result

    # ------------------------------------------------------------------ summaries

    def _summarize_repo(self, ctx: dict[str, Any]) -> RepositorySummary:
        a = ctx["analysis"]
        langs = ", ".join(f"{k} ({v} files)" for k, v in sorted(a["languages"].items(), key=lambda kv: -kv[1]))
        frameworks = ", ".join(a["frameworks"]) or "no detected framework"
        modules = sorted(a["modules"], key=lambda m: -len(m.get("symbols", [])))[:6]
        tests = ", ".join(a["test_dirs"]) or "none found"
        arch = (
            f"{ctx.get('repo_name', 'Repository')} contains {a['file_count']} files "
            f"({a['total_lines']} lines). Languages: {langs}. Frameworks: {frameworks}. "
            f"Entrypoints: {', '.join(a['entrypoints']) or 'none detected'}. Tests: {tests}."
        )
        risks = []
        if not a["test_files"]:
            risks.append("No automated tests detected; changes cannot be verified.")
        if not a["docs"]:
            risks.append("No architecture documentation found.")
        return RepositorySummary(
            architecture=arch,
            key_modules=[f"{m['path']}: {', '.join(m['symbols'][:5]) or 'no top-level symbols'}" for m in modules],
            conventions=a.get("conventions", [])[:10],
            risks=risks,
        )

    # ------------------------------------------------------------------ planning

    def _plan(self, ctx: dict[str, Any]) -> ImplementationPlan:
        scenario = detect_scenario(ctx["workflow"], ctx["request"], ctx["files"])
        if scenario == "taskboard_jwt":
            return ImplementationPlan(
                summary="Add stateless HS256 bearer-token authentication to write endpoints.",
                tasks=[
                    TaskSpec(
                        task_id="TASK-001",
                        title="Implement JWT token creation and validation",
                        description="Add a standard-library HS256 token module with signature and expiry checks.",
                        priority="high",
                        acceptance_criteria=[
                            "Reject tokens with invalid signatures",
                            "Reject expired tokens",
                            "Include unit tests",
                        ],
                        target_files=["taskboard/security.py", "tests/test_security.py"],
                        complexity="M",
                    ),
                    TaskSpec(
                        task_id="TASK-002",
                        title="Add authentication settings",
                        description="Read the signing secret and token lifetime from the environment.",
                        priority="medium",
                        acceptance_criteria=["Secret is configurable through TASKBOARD_JWT_SECRET"],
                        target_files=["taskboard/config.py"],
                        complexity="S",
                    ),
                    TaskSpec(
                        task_id="TASK-003",
                        title="Require bearer tokens on write endpoints",
                        description="Add a FastAPI dependency and apply it to create, update and delete routes.",
                        dependencies=["TASK-001", "TASK-002"],
                        priority="high",
                        acceptance_criteria=[
                            "Write endpoints return 401 without a valid token",
                            "Read endpoints remain public",
                        ],
                        target_files=["taskboard/auth.py", "taskboard/main.py"],
                        complexity="M",
                    ),
                    TaskSpec(
                        task_id="TASK-004",
                        title="Cover authentication in endpoint tests",
                        description="Authenticate the shared test client and add endpoint-level auth tests.",
                        dependencies=["TASK-003"],
                        priority="medium",
                        acceptance_criteria=["Existing tests pass with authentication enabled", "Include unit tests"],
                        target_files=["tests/conftest.py", "tests/test_auth_endpoints.py"],
                        complexity="S",
                        kind="tests",
                    ),
                ],
                risks=[
                    "A development default secret exists for local use and must be overridden in production.",
                    "Existing API clients must start sending Authorization headers for writes.",
                ],
                out_of_scope=["User registration and login endpoints", "Token revocation"],
            )
        if scenario == "taskboard_store_tests":
            return ImplementationPlan(
                summary="Add focused unit tests for TaskStore.",
                tasks=[
                    TaskSpec(
                        task_id="TASK-001",
                        title="Unit-test TaskStore behaviour",
                        description="Cover id sequencing, partial updates, filtering, deletion and reset.",
                        acceptance_criteria=["Include unit tests", "Tests exercise store edge cases"],
                        target_files=["tests/test_store.py"],
                        complexity="S",
                        kind="tests",
                    )
                ],
            )
        # Generic fallback: a mechanically derived single-task plan.
        return ImplementationPlan(
            summary=f"Single-step plan derived from the request (demo provider): {ctx['request'][:200]}",
            tasks=[
                TaskSpec(
                    task_id="TASK-001",
                    title=ctx["request"][:120] if len(ctx["request"]) >= 3 else "Requested change",
                    description=ctx["request"][:4000],
                    acceptance_criteria=["Requested behaviour is implemented", "Existing tests pass"],
                    target_files=[c["path"] for c in ctx.get("relevant", [])][:5],
                )
            ],
            risks=["The demo provider cannot synthesize code for arbitrary requests; configure a model provider."],
        )

    # ------------------------------------------------------------------ code generation

    def _codegen(self, ctx: dict[str, Any]) -> PatchProposal:
        scenario = detect_scenario(ctx["workflow"], ctx["request"], ctx["files"])
        task_id = ctx["task"]["task_id"]
        edits: list[FileEdit] = []
        if scenario == "taskboard_jwt":
            if task_id == "TASK-001":
                edits = [
                    FileEdit(path="taskboard/security.py", operation="create", content=tb.SECURITY_PY_V1),
                    FileEdit(path="tests/test_security.py", operation="create", content=tb.TEST_SECURITY_PY),
                ]
            elif task_id == "TASK-002":
                edits = [FileEdit(path="taskboard/config.py", operation="create", content=tb.CONFIG_PY)]
            elif task_id == "TASK-003":
                edits = [
                    FileEdit(path="taskboard/auth.py", operation="create", content=tb.AUTH_PY),
                    FileEdit(
                        path="taskboard/main.py",
                        operation="replace",
                        search=tb.MAIN_IMPORT_SEARCH,
                        replacement=tb.MAIN_IMPORT_REPLACEMENT,
                    ),
                    *[
                        FileEdit(path="taskboard/main.py", operation="replace", search=s, replacement=r)
                        for s, r in tb.MAIN_ROUTE_EDITS
                    ],
                ]
            elif task_id == "TASK-004":
                edits = [
                    FileEdit(
                        path="tests/conftest.py",
                        operation="replace",
                        search=tb.CONFTEST_IMPORT_SEARCH,
                        replacement=tb.CONFTEST_IMPORT_REPLACEMENT,
                    ),
                    FileEdit(
                        path="tests/conftest.py",
                        operation="replace",
                        search=tb.CONFTEST_SEARCH,
                        replacement=tb.CONFTEST_REPLACEMENT,
                    ),
                    FileEdit(
                        path="tests/test_auth_endpoints.py", operation="create", content=tb.TEST_AUTH_ENDPOINTS_PY
                    ),
                ]
        elif scenario == "taskboard_store_tests" and task_id == "TASK-001":
            edits = [FileEdit(path="tests/test_store.py", operation="create", content=tb.TEST_STORE_PY)]
        elif scenario == "taskboard_reopen" and task_id == "FIX":
            edits = [
                FileEdit(
                    path="taskboard/store.py",
                    operation="replace",
                    search=tb.STORE_FIX_SEARCH,
                    replacement=tb.STORE_FIX_REPLACEMENT,
                )
            ]
        if not edits:
            return PatchProposal(
                task_id=task_id,
                summary="No scripted change available for this request in demo mode.",
                notes=["Configure FORGEFLOW_LLM_PROVIDER to generate code for arbitrary requests."],
            )
        return PatchProposal(
            task_id=task_id,
            summary=f"Scripted demo patch for {task_id}: {ctx['task']['title']}",
            edits=edits,
            notes=["Simulated model output (demo provider)."],
        )

    def _reproduce(self, ctx: dict[str, Any]) -> PatchProposal:
        if detect_scenario("bug_investigation", ctx["request"], ctx["files"]) == "taskboard_reopen":
            return PatchProposal(
                task_id="REPRO",
                summary="Regression test: reopening a completed task via PATCH completed=false.",
                edits=[
                    FileEdit(path="tests/test_regression_reopen.py", operation="create", content=tb.REGRESSION_TEST_PY)
                ],
                notes=["Simulated model output (demo provider)."],
            )
        return PatchProposal(task_id="REPRO", summary="No scripted reproduction available in demo mode.")

    # ------------------------------------------------------------------ debugging

    def _diagnose(self, ctx: dict[str, Any]) -> Diagnosis:
        output = ctx.get("test_output", "")
        files = ctx.get("workspace_files", {})
        security = files.get("taskboard/security.py", "")
        if "token expired" in output and tb.SECURITY_FIX_SEARCH in security:
            return Diagnosis(
                root_cause=(
                    "decode_token rejects tokens whose expiry is in the future: the comparison "
                    "`exp > current` is inverted, so every valid token raises TokenError('token expired')."
                ),
                evidence=[line for line in output.splitlines() if "expired" in line][:5],
                confidence=0.9,
                fix=PatchProposal(
                    task_id="FIX",
                    summary="Invert the expiry comparison in decode_token.",
                    edits=[
                        FileEdit(
                            path="taskboard/security.py",
                            operation="replace",
                            search=tb.SECURITY_FIX_SEARCH,
                            replacement=tb.SECURITY_FIX_REPLACEMENT,
                        )
                    ],
                ),
            )
        if "binascii.Error" in output and tb.SIGNATURE_FIX_SEARCH in security:
            return Diagnosis(
                root_cause=(
                    "decode_token base64-decodes the signature segment without handling errors, so a malformed "
                    "token raises binascii.Error (surfacing as a 500) instead of TokenError (401)."
                ),
                evidence=[line for line in output.splitlines() if "binascii" in line][:5],
                confidence=0.85,
                fix=PatchProposal(
                    task_id="FIX",
                    summary="Convert signature decoding errors into TokenError.",
                    edits=[
                        FileEdit(
                            path="taskboard/security.py",
                            operation="replace",
                            search=tb.SIGNATURE_FIX_SEARCH,
                            replacement=tb.SIGNATURE_FIX_REPLACEMENT,
                        )
                    ],
                ),
            )
        store = files.get("taskboard/store.py", "")
        if "test_reopen_completed_task" in output and tb.STORE_FIX_SEARCH in store:
            return Diagnosis(
                root_cause=(
                    "TaskStore.update guards the completed field with `if data.completed:`, which is false "
                    "for an explicit `completed=False`, so the field is never cleared."
                ),
                evidence=[line for line in output.splitlines() if "assert" in line][:5],
                confidence=0.95,
                fix=PatchProposal(
                    task_id="FIX",
                    summary="Check `completed is not None` so False is applied.",
                    edits=[
                        FileEdit(
                            path="taskboard/store.py",
                            operation="replace",
                            search=tb.STORE_FIX_SEARCH,
                            replacement=tb.STORE_FIX_REPLACEMENT,
                        )
                    ],
                ),
            )
        return Diagnosis(
            root_cause="The demo provider has no scripted diagnosis for this failure.",
            evidence=[line for line in output.splitlines() if "FAILED" in line or "Error" in line][:5],
            confidence=0.0,
            give_up=True,
        )

    # ------------------------------------------------------------------ review

    def _review(self, ctx: dict[str, Any]) -> ReviewReport:
        diff: str = ctx.get("diff", "")
        findings: list[ReviewFinding] = []
        if "DEFAULT_DEV_SECRET" in diff:
            findings.append(
                ReviewFinding(
                    severity="medium",
                    category="security",
                    file="taskboard/config.py",
                    title="Development signing secret used when TASKBOARD_JWT_SECRET is unset",
                    detail="Fail closed in production (refuse to start without a configured secret).",
                )
            )
        if "hmac.compare_digest" in diff:
            findings.append(
                ReviewFinding(
                    severity="info",
                    category="security",
                    file="taskboard/security.py",
                    title="Constant-time signature comparison",
                    detail="Signature check uses hmac.compare_digest.",
                )
            )
        added_tests = len(re.findall(r"^\+def test_", diff, flags=re.M))
        summary = (
            f"Heuristic review (demo provider) of {ctx.get('files_changed', 0)} changed files; "
            f"{added_tests} new test functions."
        )
        return ReviewReport(summary=summary, findings=findings)

    def _criteria(self, ctx: dict[str, Any]) -> CriteriaAssessment:
        changed = set(ctx.get("changed_files", []))
        passed = bool(ctx.get("tests_passed"))
        checks = []
        for task in ctx.get("tasks", []):
            touched = [p for p in task.get("target_files", []) if p in changed]
            for criterion in task["acceptance_criteria"]:
                met = passed and (bool(touched) or not task.get("target_files"))
                evidence = (
                    f"Tests passed; changed {', '.join(touched) or 'no target files'}."
                    if passed
                    else "Tests did not pass."
                )
                checks.append(
                    CriterionCheck(
                        task_id=task["task_id"],
                        criterion=criterion,
                        met=met,
                        evidence=evidence + " (heuristic check, demo provider)",
                    )
                )
        return CriteriaAssessment(checks=checks)

    def _pr(self, ctx: dict[str, Any]) -> PRNarrative:
        plan = ctx.get("plan") or {}
        title = (plan.get("summary") or ctx["request"]).strip().rstrip(".")
        if len(title) > 100:
            title = title[:97] + "..."
        if len(title) < 5:
            title = f"ForgeFlow: {title}"
        tasks = plan.get("tasks", [])
        return PRNarrative(
            title=title,
            overview=f"{ctx['request'].strip()}\n\nImplemented in {len(tasks)} planned task(s) by ForgeFlow agents.",
            notable_changes=[f"{t['task_id']}: {t['title']}" for t in tasks],
        )
