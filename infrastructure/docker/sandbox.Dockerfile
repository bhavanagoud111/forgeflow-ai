# Sandbox image: runs repository tests and linters for generated changes.
# Used per-command by the docker sandbox backend, and as the sandbox-runner service in Compose.
# It never receives credentials; Compose attaches it only to an internal network.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /usr/local/bin/uv
WORKDIR /opt/forgeflow
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/src ./src
# Runner service dependencies plus the toolchain verification profiles call.
RUN uv venv /opt/venv && VIRTUAL_ENV=/opt/venv uv pip install --no-cache . \
        "pytest>=9" "ruff>=0.17" "mypy>=2.4" "fastapi>=0.110" "httpx>=0.27" "pydantic>=2"
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox
USER 10001
ENV PATH="/opt/venv/bin:$PATH" HOME=/tmp
WORKDIR /workspace
