from langgraph.types import Send

from forgeflow.orchestration import nodes
from forgeflow.orchestration.workflows import BUILDERS, after_tests, describe
from forgeflow.schemas import Workflow


def state(**kw):
    base = {"workflow": "feature", "params": {"max_debug_attempts": 2}, "debug_attempts": 0}
    base.update(kw)
    return base


def test_passing_tests_route_to_review():
    assert after_tests(state(test_run={"passed": True, "commands": [{}]})) == "review"


def test_failing_tests_route_to_debug_until_limit():
    failing = {"passed": False, "commands": [{}], "summary": "1 failed"}
    assert after_tests(state(test_run=failing, debug_attempts=0)) == "debug"
    assert after_tests(state(test_run=failing, debug_attempts=1)) == "debug"
    assert after_tests(state(test_run=failing, debug_attempts=2)) == "tests_exhausted"


def test_bug_workflow_gets_one_extra_diagnosis():
    failing = {"passed": False, "commands": [{}], "summary": ""}
    assert after_tests(state(workflow="bug_investigation", test_run=failing, debug_attempts=2)) == "debug"
    assert after_tests(state(workflow="bug_investigation", test_run=failing, debug_attempts=3)) == "tests_exhausted"


def test_outcome_short_circuits_to_report():
    assert after_tests(state(outcome="failed", test_run={"passed": False, "commands": []})) == "report"


def test_no_test_commands_route_to_review_for_verification_to_judge():
    assert after_tests(state(test_run={"passed": False, "commands": []})) == "review"


def test_approval_routing():
    assert nodes.after_approval({"approval": {"decision": "approved"}}) == "create_pr"
    assert nodes.after_approval({"approval": {"decision": "rejected"}}) == "rejected"


def test_reproduction_routing():
    assert (
        nodes.after_reproduce_tests({"test_run": {"passed": True, "commands": [], "summary": ""}}) == "not_reproduced"
    )
    assert nodes.after_reproduce_tests({"test_run": {"passed": False, "commands": [], "summary": ""}}) == "debug"


def _plan_state(batches, index):
    tasks = [
        {
            "task_id": t,
            "title": f"Task {t}",
            "description": "",
            "dependencies": [],
            "priority": "medium",
            "acceptance_criteria": ["x"],
            "target_files": [],
            "complexity": "S",
            "kind": "implementation",
        }
        for b in batches
        for t in b
    ]
    return {
        "execution_id": "exec_1",
        "workflow": "feature",
        "request": "r",
        "workspace_id": "w",
        "branch": "b",
        "plan": {"summary": "s", "tasks": tasks, "risks": [], "out_of_scope": []},
        "batches": batches,
        "batch_index": index,
        "analysis": {"modules": [], "root_files": [], "conventions": []},
    }


def test_dispatch_fans_out_current_batch_in_parallel():
    sends = nodes.dispatch_batch(_plan_state([["TASK-001", "TASK-002"], ["TASK-003"]], 0))
    assert isinstance(sends, list) and all(isinstance(s, Send) for s in sends)
    assert [s.arg["task"]["task_id"] for s in sends] == ["TASK-001", "TASK-002"]
    assert all(s.node == "generate_task" for s in sends)


def test_dispatch_moves_to_tests_when_batches_done():
    assert nodes.dispatch_batch(_plan_state([["TASK-001"]], 1)) == "run_tests"


def test_all_workflows_compile_with_expected_entry_and_exit():
    for wf in BUILDERS:
        graph = describe(wf)
        ids = {n["id"] for n in graph["nodes"]}
        assert "report" in ids
    feature = {n["id"] for n in describe(Workflow.feature)["nodes"]}
    assert {"plan", "generate_task", "debug", "review", "verify", "request_approval", "create_pr"} <= feature
    bug = {n["id"] for n in describe(Workflow.bug_investigation)["nodes"]}
    assert {"reproduce", "not_reproduced"} <= bug and "plan" not in bug
    assert {n["id"] for n in describe(Workflow.code_review)["nodes"]} == {
        "load_diff",
        "review",
        "review_done",
        "report",
    }
