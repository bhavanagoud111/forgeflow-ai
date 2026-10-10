"""Task dependency resolution."""

from __future__ import annotations

from forgeflow.schemas import TaskSpec


class DependencyCycle(ValueError):
    pass


def resolve_batches(tasks: list[TaskSpec], max_parallel: int = 4) -> list[list[str]]:
    """Group tasks into ordered batches; tasks within a batch are independent.

    Kahn's algorithm by levels. Within a level tasks are ordered by priority then id so the
    result is deterministic. Levels wider than ``max_parallel`` are split.
    """
    ids = {t.task_id for t in tasks}
    remaining = {t.task_id: {d for d in t.dependencies if d in ids} for t in tasks}
    unknown = {d for t in tasks for d in t.dependencies if d not in ids}
    if unknown:
        raise ValueError(f"unknown dependencies: {sorted(unknown)}")
    rank = {"high": 0, "medium": 1, "low": 2}
    by_id = {t.task_id: t for t in tasks}
    batches: list[list[str]] = []
    done: set[str] = set()
    while remaining:
        ready = sorted(
            (tid for tid, deps in remaining.items() if deps <= done),
            key=lambda tid: (rank[by_id[tid].priority.value], tid),
        )
        if not ready:
            raise DependencyCycle(f"dependency cycle among {sorted(remaining)}")
        for i in range(0, len(ready), max(1, max_parallel)):
            batches.append(ready[i : i + max_parallel])
        for tid in ready:
            done.add(tid)
            del remaining[tid]
    return batches
