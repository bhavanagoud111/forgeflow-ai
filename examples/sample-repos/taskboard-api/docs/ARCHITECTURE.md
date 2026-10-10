# Architecture

- `taskboard/main.py` defines the FastAPI application and HTTP routes.
- `taskboard/models.py` holds the Pydantic request and response models.
- `taskboard/store.py` is an in-memory repository behind a small `TaskStore` class.
- Tests live in `tests/` and use FastAPI's `TestClient`.

The store is injected through a module-level instance so tests can reset it.
