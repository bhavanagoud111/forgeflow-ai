from taskboard.models import Task, TaskCreate, TaskUpdate


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def list(self, completed: bool | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if completed is not None:
            tasks = [t for t in tasks if t.completed == completed]
        return tasks

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)

    def create(self, data: TaskCreate) -> Task:
        task = Task(id=self._next_id, title=data.title, description=data.description)
        self._tasks[task.id] = task
        self._next_id += 1
        return task

    def update(self, task_id: int, data: TaskUpdate) -> Task | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.completed:
            task.completed = data.completed
        return task

    def delete(self, task_id: int) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def reset(self) -> None:
        self._tasks.clear()
        self._next_id = 1
