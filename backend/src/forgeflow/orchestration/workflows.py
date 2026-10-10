"""Workflow graph definitions.

Five workflows are assembled from shared node groups instead of one graph with every
feature. ``_implementation_loop`` (parallel code generation, tests, bounded debugging)
and ``_delivery`` (review, verification, approval, pull request) are reused.

Feature implementation:

    prepare_workspace -> analyze -> plan -> resolve_dependencies
      -> [generate_task x N in parallel] -> apply_batch -> (next batch | run_tests)
      run_tests -> pass: review | fail: debug -> run_tests (bounded) | exhausted: report
      review -> critical: report | verify -> incomplete: report | draft_pr -> request_approval
      request_approval -> approved: create_pr -> report | rejected -> report
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from forgeflow.llm.base import LLMError
from forgeflow.orchestration import nodes as n
from forgeflow.orchestration.runtime import Ctx
from forgeflow.orchestration.state import ExecutionState
from forgeflow.schemas import Workflow


def _transient(exc: BaseException) -> bool:
    import httpx

    return isinstance(exc, (httpx.TransportError, ConnectionError)) or (
        isinstance(exc, LLMError) and "timeout" in str(exc).lower()
    )


RETRY = RetryPolicy(max_attempts=2, initial_interval=2.0, retry_on=_transient)

Builder = StateGraph[ExecutionState, Ctx, ExecutionState, ExecutionState]


def _new() -> Builder:
    return StateGraph(ExecutionState, context_schema=Ctx)


def _if_outcome(next_node: str):  # type: ignore[no-untyped-def]
    def route(state: ExecutionState) -> str:
        return "report" if state.get("outcome") else next_node

    route.__name__ = f"outcome_or_{next_node}"
    return route


def after_tests(state: ExecutionState) -> str:
    if state.get("outcome"):
        return "report"
    tr = state["test_run"]
    if tr["passed"] or not tr["commands"]:
        return "review"
    limit = n.debug_limit(state, int(state["params"].get("max_debug_attempts", 2)))
    return "debug" if state.get("debug_attempts", 0) < limit else "tests_exhausted"


async def tests_exhausted(state: ExecutionState) -> dict[str, Any]:
    return {
        "outcome": "failed",
        "outcome_reason": f"Tests still failing after {state.get('debug_attempts', 0)} debugging attempt(s): "
        f"{state['test_run']['summary'][:500]}",
    }


def _implementation_loop(b: Builder) -> None:
    b.add_node("resolve_dependencies", n.resolve_dependencies)
    b.add_node("generate_task", n.generate_task, retry_policy=RETRY)  # type: ignore[call-overload]
    b.add_node("apply_batch", n.apply_batch)
    _test_debug_loop(b)
    b.add_conditional_edges("resolve_dependencies", n.dispatch_batch, ["generate_task", "run_tests"])
    b.add_edge("generate_task", "apply_batch")
    b.add_conditional_edges("apply_batch", n.dispatch_batch, ["generate_task", "run_tests"])


def _test_debug_loop(b: Builder) -> None:
    b.add_node("run_tests", n.run_tests)
    b.add_node("debug", n.debug, retry_policy=RETRY)
    b.add_node("tests_exhausted", tests_exhausted)
    b.add_conditional_edges("run_tests", after_tests, ["review", "debug", "tests_exhausted", "report"])
    b.add_conditional_edges("debug", _if_outcome("run_tests"), ["run_tests", "report"])
    b.add_edge("tests_exhausted", "report")


def _delivery(b: Builder) -> None:
    b.add_node("review", n.review, retry_policy=RETRY)
    b.add_node("verify", n.verify, retry_policy=RETRY)
    b.add_node("draft_pr", n.draft_pr, retry_policy=RETRY)
    b.add_node("request_approval", n.request_approval)
    b.add_node("create_pr", n.create_pr)
    b.add_node("rejected", n.rejected)
    b.add_node("report", n.report)
    b.add_conditional_edges("review", _if_outcome("verify"), ["verify", "report"])
    b.add_conditional_edges("verify", _if_outcome("draft_pr"), ["draft_pr", "report"])
    b.add_edge("draft_pr", "request_approval")
    b.add_conditional_edges("request_approval", n.after_approval, ["create_pr", "rejected"])
    b.add_edge("create_pr", "report")
    b.add_edge("rejected", "report")
    b.add_edge("report", END)


def _prefix(b: Builder) -> None:
    b.add_node("prepare_workspace", n.prepare_workspace, retry_policy=RETRY)
    b.add_node("analyze", n.analyze, retry_policy=RETRY)
    b.add_edge(START, "prepare_workspace")
    b.add_edge("prepare_workspace", "analyze")


def feature_graph() -> Builder:
    b = _new()
    _prefix(b)
    b.add_node("plan", n.plan, retry_policy=RETRY)
    b.add_edge("analyze", "plan")
    b.add_edge("plan", "resolve_dependencies")
    _implementation_loop(b)
    _delivery(b)
    return b


def test_generation_graph() -> Builder:
    # Same shape as feature delivery; the planner runs in test-only mode and apply_batch
    # rejects edits outside test files.
    return feature_graph()


def bug_investigation_graph() -> Builder:
    b = _new()
    _prefix(b)
    b.add_node("reproduce", n.reproduce, retry_policy=RETRY)
    b.add_node("reproduce_tests", n.run_tests)
    b.add_node("not_reproduced", n.not_reproduced)
    b.add_edge("analyze", "reproduce")
    b.add_conditional_edges("reproduce", _if_outcome("reproduce_tests"), ["reproduce_tests", "report"])
    b.add_conditional_edges("reproduce_tests", n.after_reproduce_tests, ["debug", "not_reproduced", "report"])
    b.add_edge("not_reproduced", "report")
    _test_debug_loop(b)
    _delivery(b)
    return b


def code_review_graph() -> Builder:
    b = _new()
    b.add_node("load_diff", n.load_diff, retry_policy=RETRY)
    b.add_node("review", n.review, retry_policy=RETRY)
    b.add_node("review_done", n.review_done)
    b.add_node("report", n.report)
    b.add_edge(START, "load_diff")
    b.add_edge("load_diff", "review")
    b.add_edge("review", "review_done")
    b.add_edge("review_done", "report")
    b.add_edge("report", END)
    return b


def repo_onboarding_graph() -> Builder:
    b = _new()
    _prefix(b)
    b.add_node("onboarding_done", n.onboarding_done)
    b.add_node("report", n.report)
    b.add_edge("analyze", "onboarding_done")
    b.add_edge("onboarding_done", "report")
    b.add_edge("report", END)
    return b


BUILDERS = {
    Workflow.feature: feature_graph,
    Workflow.bug_investigation: bug_investigation_graph,
    Workflow.code_review: code_review_graph,
    Workflow.repo_onboarding: repo_onboarding_graph,
    Workflow.test_generation: test_generation_graph,
}


def describe(workflow: Workflow) -> dict[str, Any]:
    """Nodes and edges of a workflow graph, for the UI's workflow visualisation."""
    g = BUILDERS[workflow]().compile().get_graph()
    return {
        "nodes": [{"id": node_id} for node_id in g.nodes if node_id not in ("__start__", "__end__")],
        "edges": [
            {"source": e.source, "target": e.target, "conditional": e.conditional}
            for e in g.edges
            if e.source != "__start__" and e.target != "__end__"
        ],
    }
