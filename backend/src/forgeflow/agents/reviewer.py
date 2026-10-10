"""Code Review Agent: deterministic static checks plus a model review."""

from __future__ import annotations

import re

from forgeflow.agents.base import Services
from forgeflow.schemas import ReviewFinding, ReviewReport, Severity
from forgeflow.security.redaction import has_secret_assignment, has_token_format_secret
from forgeflow.security.untrusted import fence, injection_signals
from forgeflow.telemetry import RunHandle

SYSTEM = (
    "You are the Code Review Agent. Review the unified diff for correctness bugs, security problems, "
    "maintainability issues, missing tests and changes outside the task scope. Report concrete findings with "
    "file and line where possible. Use 'critical' only for issues that must block merging (for example "
    "credential leaks, auth bypasses, data loss or code that cannot work). Do not report style nits."
)

_RULES: list[tuple[re.Pattern[str], Severity, str, str, str]] = [
    (
        re.compile(r"\beval\(|\bexec\("),
        Severity.high,
        "security",
        "Dynamic code execution",
        "eval/exec on runtime data allows code injection.",
    ),
    (
        re.compile(r"shell\s*=\s*True"),
        Severity.high,
        "security",
        "Shell invocation",
        "subprocess with shell=True is vulnerable to command injection.",
    ),
    (
        re.compile(r"verify\s*=\s*False|ssl\s*=\s*False|InsecureRequestWarning"),
        Severity.high,
        "security",
        "TLS verification disabled",
        "Disabling certificate verification enables man-in-the-middle attacks.",
    ),
    (
        re.compile(r"pickle\.loads?\(|yaml\.load\((?!.*SafeLoader)"),
        Severity.medium,
        "security",
        "Unsafe deserialization",
        "Deserializing untrusted data can execute code.",
    ),
    (
        re.compile(r"except\s*:\s*$|except Exception:\s*pass"),
        Severity.low,
        "correctness",
        "Swallowed exception",
        "Silently ignoring exceptions hides failures.",
    ),
    (
        re.compile(r"\b(TODO|FIXME|XXX)\b"),
        Severity.info,
        "maintainability",
        "Unresolved marker",
        "The change adds a TODO/FIXME marker.",
    ),
    (
        re.compile(r"@pytest\.mark\.skip|\.skip\(|xit\(|it\.skip"),
        Severity.medium,
        "tests",
        "Test skipped",
        "The change skips a test instead of fixing it.",
    ),
]


def _is_test_path(path: str) -> bool:
    return bool(re.search(r"(^|/)(tests?/|test_|__tests__/|conftest\.py$)|\.(test|spec)\.", path))


def parse_diff(diff: str) -> dict[str, list[tuple[int, str, str]]]:
    """Map file -> [(new_line_no, sign, text)] for added and removed lines."""
    files: dict[str, list[tuple[int, str, str]]] = {}
    current: str | None = None
    line_no = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current = None if path == "/dev/null" else path.removeprefix("b/")
            if current:
                files.setdefault(current, [])
        elif raw.startswith("--- "):
            old = raw[4:].strip()
            if old != "/dev/null":
                files.setdefault(old.removeprefix("a/"), [])
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line_no = int(m.group(1)) if m else 0
        elif current is not None:
            if raw.startswith("+"):
                files[current].append((line_no, "+", raw[1:]))
                line_no += 1
            elif raw.startswith("-"):
                files[current].append((line_no, "-", raw[1:]))
            else:
                line_no += 1
    return files


def static_findings(diff: str, changed: list[dict[str, str]]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    parsed = parse_diff(diff)
    for path, lines in parsed.items():
        for line_no, sign, text in lines:
            if sign != "+":
                continue
            if has_token_format_secret(text):
                findings.append(
                    ReviewFinding(
                        severity=Severity.critical,
                        category="security",
                        file=path,
                        line=line_no,
                        source="static",
                        title="Credential committed",
                        detail="An added line contains a token in a known credential format.",
                    )
                )
            elif has_secret_assignment(text) and not _is_test_path(path):
                findings.append(
                    ReviewFinding(
                        severity=Severity.medium,
                        category="security",
                        file=path,
                        line=line_no,
                        source="static",
                        title="Hard-coded secret-like value",
                        detail="A literal is assigned to a secret-looking name. Confirm it is not a real credential.",
                    )
                )
            for pattern, sev, cat, title, detail in _RULES:
                if pattern.search(text):
                    findings.append(
                        ReviewFinding(
                            severity=sev,
                            category=cat,
                            file=path,
                            line=line_no,  # type: ignore[arg-type]
                            title=title,
                            detail=detail,
                            source="static",
                        )
                    )
            for signal in injection_signals(text):
                findings.append(
                    ReviewFinding(
                        severity=Severity.medium,
                        category="security",
                        file=path,
                        line=line_no,
                        source="static",
                        title="Prompt-injection style text added",
                        detail=f"Added content contains '{signal}'. Confirm it is intended.",
                    )
                )
    for c in changed:
        p = c["path"]
        if p.startswith(".github/workflows/"):
            findings.append(
                ReviewFinding(
                    severity=Severity.high,
                    category="scope",
                    file=p,
                    source="static",
                    title="CI configuration changed",
                    detail="Generated changes must not modify CI pipelines.",
                )
            )
        if c["status"] == "deleted" and re.search(r"(^|/)(tests?/|test_)", p):
            findings.append(
                ReviewFinding(
                    severity=Severity.high,
                    category="tests",
                    file=p,
                    source="static",
                    title="Test file deleted",
                    detail="Removing tests reduces coverage.",
                )
            )
    src = [
        c
        for c in changed
        if not re.search(r"(^|/)(tests?/|test_|__tests__)|\.(test|spec)\.", c["path"])
        and c["path"].endswith((".py", ".ts", ".tsx", ".js", ".go"))
    ]
    tests = [c for c in changed if c not in src and re.search(r"test", c["path"])]
    if src and not tests:
        findings.append(
            ReviewFinding(
                severity=Severity.low,
                category="tests",
                source="static",
                title="No test changes",
                detail="Source files changed without test updates.",
            )
        )
    added = sum(1 for lines in parsed.values() for _, s, _ in lines if s == "+")
    if added > 1500:
        findings.append(
            ReviewFinding(
                severity=Severity.low,
                category="maintainability",
                source="static",
                title="Large change",
                detail=f"{added} added lines; consider splitting.",
            )
        )
    return findings


async def review(
    svc: Services, run: RunHandle, *, diff: str, changed: list[dict[str, str]], request: str, plan_summary: str
) -> ReviewReport:
    async with svc.recorder.tool_call(run, "diff.static_checks", {"files": len(changed)}) as res:
        static = static_findings(diff, changed)
        res["summary"] = f"{len(static)} static findings"
    model_report = await svc.llm.structured(
        ReviewReport,
        purpose="review",
        system=SYSTEM,
        prompt=(
            f"Request:\n{fence('request', request, 4000)}\n\nPlan: {plan_summary}\n\n"
            f"Diff:\n{fence('diff', diff, 80_000)}"
        ),
        run=run,
        context={"diff": diff, "files_changed": len(changed)},
    )
    model_findings = [f.model_copy(update={"source": "model"}) for f in model_report.findings]
    return ReviewReport(summary=model_report.summary, findings=static + model_findings)
