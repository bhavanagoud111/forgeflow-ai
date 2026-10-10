# Contributing

## Setup

```bash
make setup           # uv sync (backend) + npm ci (web)
make api             # API + embedded worker on :8000 (demo provider)
make web             # web UI on :3000
```

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, Docker (for the
container sandbox and Compose).

## Checks

Run before opening a pull request:

```bash
make lint typecheck test
make test-docker     # sandbox isolation tests (needs Docker)
```

CI runs the same commands plus dependency auditing and secret scanning.

## Guidelines

- Keep agent outputs typed: add or extend a Pydantic model in `backend/src/forgeflow/schemas.py`
  rather than passing free-form text between agents.
- New graph nodes belong in `orchestration/nodes.py`; routing functions must depend only on state.
- Anything that reaches outside the workspace (GitHub, Slack, network) must go through an
  integration module and, if it writes, through the approval gate.
- Never weaken the command allowlist or sandbox flags without a matching test and a note in
  `SECURITY.md`.
- Describe only implemented behaviour in documentation. Mark experimental features as such.
- Database changes need an Alembic migration (`uv run alembic revision --autogenerate -m "..."`).
