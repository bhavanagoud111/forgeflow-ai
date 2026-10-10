# Taskboard API

A deliberately small FastAPI service for tracking tasks. ForgeFlow uses it as a sample
repository for demos and end-to-end tests.

```bash
pip install fastapi httpx pytest
python -m pytest -q
uvicorn taskboard.main:app --reload
```

Known issue (left in on purpose for the bug-investigation demo): `PATCH /tasks/{id}`
with `{"completed": false}` does not reopen a completed task.
