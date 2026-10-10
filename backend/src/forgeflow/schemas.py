"""Validated domain models exchanged between agents.

Agent outputs are always parsed into these models before they reach graph state, so a
malformed model response fails loudly instead of becoming a workflow instruction.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TASK_ID = re.compile(r"^TASK-\d{3}$")
_REL_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_./@+-]+$")


def validate_rel_path(path: str) -> str:
    p = path.strip()
    if not p or not _REL_PATH.match(p) or p.startswith(".git/") or p == ".git":
        raise ValueError(f"invalid repository-relative path: {path!r}")
    return p


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------- analysis


class ModuleSummary(Strict):
    path: str
    language: str
    symbols: list[str] = Field(default_factory=list, max_length=50)
    imports: list[str] = Field(default_factory=list, max_length=50)
    lines: int = 0


class RepositoryAnalysis(Strict):
    """Static analysis produced by the Repository Analyst. No LLM involved."""

    root_files: list[str]
    languages: dict[str, int]  # language -> file count
    frameworks: list[str]
    package_managers: list[str]
    test_dirs: list[str]
    test_files: list[str]
    docs: list[str]
    entrypoints: list[str]
    modules: list[ModuleSummary]
    import_graph: dict[str, list[str]]
    verification_profile: list[list[str]]  # allowlisted argv lists
    lint_profile: list[list[str]] = Field(default_factory=list)
    file_count: int
    total_lines: int
    conventions: list[str] = Field(default_factory=list)


class CodeContext(Strict):
    path: str
    start_line: int
    end_line: int
    score: float
    content: str


class RepositorySummary(Strict):
    """LLM (or demo) narrative over the static analysis."""

    architecture: str = Field(max_length=4000)
    key_modules: list[str] = Field(default_factory=list, max_length=20)
    conventions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)


# ----------------------------------------------------------------- planning


class Priority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskSpec(Strict):
    task_id: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(max_length=4000)
    dependencies: list[str] = Field(default_factory=list)
    priority: Priority = Priority.medium
    acceptance_criteria: list[str] = Field(min_length=1, max_length=12)
    target_files: list[str] = Field(default_factory=list, max_length=20)
    complexity: Literal["S", "M", "L"] = "M"
    kind: Literal["implementation", "tests", "docs", "refactor", "fix"] = "implementation"

    @field_validator("task_id")
    @classmethod
    def _task_id(cls, v: str) -> str:
        if not _TASK_ID.match(v):
            raise ValueError("task_id must look like TASK-001")
        return v

    @field_validator("target_files")
    @classmethod
    def _paths(cls, v: list[str]) -> list[str]:
        return [validate_rel_path(p) for p in v]


class ImplementationPlan(Strict):
    summary: str = Field(max_length=2000)
    tasks: list[TaskSpec] = Field(min_length=1, max_length=12)
    risks: list[str] = Field(default_factory=list, max_length=12)
    out_of_scope: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _deps_exist(self) -> ImplementationPlan:
        ids = [t.task_id for t in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task_id in plan")
        for t in self.tasks:
            for d in t.dependencies:
                if d not in ids:
                    raise ValueError(f"{t.task_id} depends on unknown task {d}")
                if d == t.task_id:
                    raise ValueError(f"{t.task_id} depends on itself")
        return self


# ----------------------------------------------------------------- code changes


class FileEdit(Strict):
    """One focused change. ``replace`` edits are preferred over full rewrites."""

    path: str
    operation: Literal["create", "replace", "rewrite", "delete"]
    # For "replace": exact text to find (must match exactly once) and its replacement.
    search: str | None = None
    replacement: str | None = None
    # For "create" / "rewrite": full file content.
    content: str | None = None

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        return validate_rel_path(v)

    @model_validator(mode="after")
    def _shape(self) -> FileEdit:
        if self.operation == "replace" and (self.search is None or self.replacement is None):
            raise ValueError("replace edits need search and replacement")
        if self.operation in ("create", "rewrite") and self.content is None:
            raise ValueError(f"{self.operation} edits need content")
        return self


class PatchProposal(Strict):
    task_id: str
    summary: str = Field(max_length=2000)
    edits: list[FileEdit] = Field(default_factory=list, max_length=25)
    notes: list[str] = Field(default_factory=list, max_length=10)


class CommandResult(Strict):
    argv: list[str]
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    timed_out: bool = False
    sandbox: str


class TestRun(Strict):
    passed: bool
    commands: list[CommandResult]
    summary: str
    failed_tests: list[str] = Field(default_factory=list)


class Diagnosis(Strict):
    root_cause: str = Field(max_length=3000)
    evidence: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)
    fix: PatchProposal | None = None
    give_up: bool = False


# ----------------------------------------------------------------- review / verification


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReviewFinding(Strict):
    severity: Severity
    category: Literal["correctness", "security", "maintainability", "tests", "scope", "performance"]
    file: str | None = None
    line: int | None = None
    title: str = Field(max_length=200)
    detail: str = Field(max_length=2000)
    source: Literal["static", "model"] = "model"


class ReviewReport(Strict):
    summary: str = Field(max_length=2000)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=50)

    @property
    def blocking(self) -> bool:
        return any(f.severity == Severity.critical for f in self.findings)


class CriterionCheck(Strict):
    task_id: str
    criterion: str
    met: bool
    evidence: str = Field(max_length=1000)


class VerificationReport(Strict):
    complete: bool
    tests_passed: bool
    lint_passed: bool | None = None
    criteria: list[CriterionCheck] = Field(default_factory=list)
    commands: list[CommandResult] = Field(default_factory=list)
    summary: str


class CriteriaAssessment(Strict):
    """LLM judgement of acceptance criteria against the diff and test output."""

    checks: list[CriterionCheck]


class PullRequestDraft(Strict):
    title: str = Field(min_length=5, max_length=120)
    body: str = Field(max_length=20_000)
    branch: str
    labels: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("branch")
    @classmethod
    def _branch(cls, v: str) -> str:
        if not re.match(r"^forgeflow/[A-Za-z0-9._/-]+$", v) or ".." in v:
            raise ValueError("ForgeFlow only writes to forgeflow/* branches")
        return v


class Workflow(StrEnum):
    feature = "feature"
    bug_investigation = "bug_investigation"
    code_review = "code_review"
    repo_onboarding = "repo_onboarding"
    test_generation = "test_generation"


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "blocked", "rejected", "cancelled"})


class PRNarrative(Strict):
    """Model-written part of a pull request. Verification sections are generated by code."""

    title: str = Field(min_length=5, max_length=100)
    overview: str = Field(max_length=3000)
    notable_changes: list[str] = Field(default_factory=list, max_length=15)
