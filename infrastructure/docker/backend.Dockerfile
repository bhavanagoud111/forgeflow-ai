# ForgeFlow API / worker image.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /usr/local/bin/uv
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --extra anthropic --extra openai --no-install-project
COPY backend/src ./src
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN uv sync --frozen --no-dev --extra anthropic --extra openai
COPY examples /app/examples

RUN useradd --uid 10001 --create-home forgeflow && mkdir -p /data/workspaces && chown -R forgeflow /data
USER forgeflow
ENV PATH="/app/backend/.venv/bin:$PATH" FORGEFLOW_WORKSPACE_ROOT=/data/workspaces
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn forgeflow.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
