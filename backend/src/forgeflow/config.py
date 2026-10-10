"""Runtime configuration.

Every setting is read from the environment with the ``FORGEFLOW_`` prefix
(for example ``FORGEFLOW_DATABASE_URL``). Secrets are typed as ``SecretStr``
so they never appear in reprs, logs or API responses.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from typing import Any

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORGEFLOW_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./forgeflow.db"
    # LangGraph checkpoints. Defaults to a SQLite file next to the app database;
    # point it at Postgres (postgresql://...) in production.
    checkpoint_url: str = "sqlite:///./forgeflow-checkpoints.db"
    redis_url: str | None = None

    # Authentication. The bootstrap admin token is hashed and stored on startup.
    admin_token: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # LLM provider. "demo" is a deterministic, offline provider for demos and tests.
    llm_provider: Literal["demo", "anthropic", "openai", "ollama"] = "demo"
    llm_model: str = "claude-opus-5-5"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_max_tokens: int = 16000
    llm_timeout_seconds: float = 300.0

    # Execution limits.
    execution_timeout_seconds: int = 1800
    node_timeout_seconds: int = 600
    max_debug_attempts: int = 2
    max_parallel_tasks: int = 4
    max_patch_files: int = 25
    max_file_bytes: int = 200_000
    embedded_worker: bool = True
    worker_poll_seconds: float = 1.0

    # Workspaces and sandboxing.
    workspace_root: Path = Path("./.forgeflow/workspaces")
    workspace_retention_hours: int = 24
    sandbox_mode: Literal["docker", "runner", "local"] = "local"
    sandbox_image: str = "forgeflow-sandbox:latest"
    sandbox_cpus: float = 1.0
    sandbox_memory_mb: int = 1024
    sandbox_pids_limit: int = 256
    sandbox_command_timeout_seconds: int = 300
    sandbox_runner_url: str = "http://sandbox-runner:8700"
    sandbox_runner_token: SecretStr | None = None
    # The local sandbox only scrubs env, applies rlimits and timeouts. It is not
    # an isolation boundary, so it refuses model-generated code unless opted in.
    allow_unsafe_local_sandbox: bool = False
    allow_dependency_install: bool = False
    local_repo_roots: list[Path] = Field(default_factory=lambda: [REPO_ROOT / "examples" / "sample-repos"])

    # GitHub. Either a token (PAT / OAuth) or a GitHub App.
    github_token: SecretStr | None = None
    github_app_id: str | None = None
    github_app_private_key: SecretStr | None = None
    github_app_installation_id: str | None = None
    github_api_url: str = "https://api.github.com"

    # Slack.
    slack_signing_secret: SecretStr | None = None
    slack_bot_token: SecretStr | None = None
    # Slack user ID -> ForgeFlow role. Users not listed are rejected.
    slack_user_roles: dict[str, Literal["viewer", "operator", "admin"]] = Field(default_factory=dict)

    # Observability.
    otel_exporter_otlp_endpoint: str | None = None
    otel_console: bool = False

    # Rate limiting (requests per minute per principal).
    rate_limit_per_minute: int = 240

    # Retention.
    event_retention_days: int = 30
    history_retention_days: int = 180

    @model_validator(mode="before")
    @classmethod
    def _blank_is_unset(cls, data: Any) -> Any:
        """Treat empty environment values (common in Compose files) as unset."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token or (self.github_app_id and self.github_app_private_key))

    @property
    def slack_configured(self) -> bool:
        return self.slack_signing_secret is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
