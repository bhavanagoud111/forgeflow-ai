import pytest

from forgeflow.orchestration.deps import DependencyCycle, resolve_batches
from forgeflow.schemas import ImplementationPlan, TaskSpec


def task(tid: str, deps: list[str] | None = None, priority: str = "medium") -> TaskSpec:
    return TaskSpec(
        task_id=tid,
        title=f"Task {tid}",
        description="d",
        dependencies=deps or [],
        priority=priority,
        acceptance_criteria=["done"],
    )


def test_independent_tasks_share_a_batch_ordered_by_priority():
    tasks = [task("TASK-001", priority="low"), task("TASK-002", priority="high"), task("TASK-003", ["TASK-001"])]
    assert resolve_batches(tasks) == [["TASK-002", "TASK-001"], ["TASK-003"]]


def test_diamond_dependencies():
    tasks = [
        task("TASK-001"),
        task("TASK-002", ["TASK-001"]),
        task("TASK-003", ["TASK-001"]),
        task("TASK-004", ["TASK-002", "TASK-003"]),
    ]
    assert resolve_batches(tasks) == [["TASK-001"], ["TASK-002", "TASK-003"], ["TASK-004"]]


def test_wide_levels_are_split_by_parallel_limit():
    tasks = [task(f"TASK-00{i}") for i in range(1, 6)]
    assert [len(b) for b in resolve_batches(tasks, max_parallel=2)] == [2, 2, 1]


def test_cycles_are_rejected():
    tasks = [task("TASK-001", ["TASK-002"]), task("TASK-002", ["TASK-001"])]
    with pytest.raises(DependencyCycle):
        resolve_batches(tasks)


def test_plan_validation_rejects_unknown_and_self_dependencies():
    with pytest.raises(ValueError, match="unknown task"):
        ImplementationPlan(summary="s", tasks=[task("TASK-001", ["TASK-009"])])
    with pytest.raises(ValueError, match="itself"):
        ImplementationPlan(summary="s", tasks=[task("TASK-001", ["TASK-001"])])
    with pytest.raises(ValueError, match="duplicate"):
        ImplementationPlan(summary="s", tasks=[task("TASK-001"), task("TASK-001")])


def test_task_ids_and_paths_are_validated():
    with pytest.raises(ValueError):
        TaskSpec(task_id="T1", title="bad id", description="", acceptance_criteria=["x"])
    with pytest.raises(ValueError):
        TaskSpec(
            task_id="TASK-001",
            title="escape",
            description="",
            acceptance_criteria=["x"],
            target_files=["../etc/passwd"],
        )
    with pytest.raises(ValueError):
        TaskSpec(task_id="TASK-001", title="no criteria", description="", acceptance_criteria=[])
