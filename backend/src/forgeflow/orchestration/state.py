"""Typed graph state.

State values are plain JSON-compatible data so checkpoints are portable across
processes and versions. Every value is produced by validating a Pydantic model at a
node boundary (see ``schemas``), and nodes re-validate what they read.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ExecutionState(TypedDict, total=False):
    # Identity and request (set at start).
    execution_id: str
    workflow: str
    repository_id: str
    repo_name: str
    repo_provider: str
    request: str
    params: dict[str, Any]

    # Workspace.
    workspace_id: str
    branch: str
    base_branch: str
    base_sha: str

    # Analysis and planning.
    analysis: dict[str, Any]
    summary: dict[str, Any]
    relevant: list[dict[str, Any]]
    plan: dict[str, Any]
    batches: list[list[str]]
    batch_index: int

    # Implementation. ``proposals`` is appended to concurrently by parallel task nodes.
    proposals: Annotated[list[dict[str, Any]], operator.add]
    applied: list[dict[str, Any]]
    reproduction: dict[str, Any]
    test_run: dict[str, Any]
    test_runs: int
    debug_attempts: int
    diagnoses: list[dict[str, Any]]

    # Review, verification and delivery.
    diff: str
    changed: list[dict[str, str]]
    review: dict[str, Any]
    verification: dict[str, Any]
    pr_draft: dict[str, Any]
    approval: dict[str, Any]
    pr: dict[str, Any]

    # Outcome.
    outcome: str  # succeeded | failed | blocked | rejected
    outcome_reason: str
    report: dict[str, Any]


class TaskPayload(TypedDict):
    """Input for one parallel code-generation branch (sent with ``Send``)."""

    execution_id: str
    workflow: str
    request: str
    task: dict[str, Any]
    workspace_id: str
    branch: str
    files: list[str]
    conventions: list[str]
    relevant: list[dict[str, Any]]
