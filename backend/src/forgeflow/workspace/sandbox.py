"""Sandboxed command execution.

Three backends share one interface:

* ``docker``  - each command runs in a throwaway container: no network, read-only root
  filesystem, all capabilities dropped, non-root user, CPU/memory/PID limits, and only
  the workspace mounted. Nothing from the host environment is passed in.
* ``runner``  - commands are sent to the ``sandbox-runner`` service (used by Docker
  Compose). The runner has no credentials and sits on an internal-only network.
* ``local``   - subprocess with a scrubbed environment, rlimits and a timeout. This is
  NOT an isolation boundary; it exists for tests and the scripted demo, and refuses
  model-generated code unless explicitly allowed.

All backends validate the command against ``security.command_policy`` first.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from typing import Protocol

import httpx

from forgeflow.config import Settings
from forgeflow.schemas import CommandResult
from forgeflow.security.command_policy import validate_command
from forgeflow.security.redaction import redact

MAX_OUTPUT = 64_000


class SandboxError(RuntimeError):
    pass


class Sandbox(Protocol):
    name: str

    async def run(self, workspace: Path, argv: list[str], timeout: int) -> CommandResult: ...


def _truncate(data: bytes) -> str:
    text = data.decode(errors="replace")
    if len(text) > MAX_OUTPUT:
        text = text[: MAX_OUTPUT // 2] + "\n...[output truncated]...\n" + text[-MAX_OUTPUT // 2 :]
    return redact(text)


class LocalSandbox:
    name = "local"

    def __init__(self, settings: Settings, python: str | None = None) -> None:
        self.settings = settings
        self.python = python or sys.executable

    def _preexec(self) -> None:  # pragma: no cover - runs in the child
        import resource

        cpu = self.settings.sandbox_command_timeout_seconds + 5
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
        if sys.platform.startswith("linux"):
            mem = self.settings.sandbox_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))

    async def run(self, workspace: Path, argv: list[str], timeout: int) -> CommandResult:
        validate_command(argv, allow_dependency_install=self.settings.allow_dependency_install)
        real = [self.python, *argv[1:]] if argv[0] == "python" else argv
        home = workspace.parent / "home"
        home.mkdir(exist_ok=True)
        env = {
            "PATH": os.pathsep.join([str(Path(self.python).parent), "/usr/local/bin", "/usr/bin", "/bin"]),
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(workspace),
            "NO_COLOR": "1",
            "CI": "1",
        }
        start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *real,
            cwd=workspace,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=self._preexec,
        )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = await proc.communicate()
        except asyncio.CancelledError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
        return CommandResult(
            argv=argv,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=int((time.perf_counter() - start) * 1000),
            stdout=_truncate(out),
            stderr=_truncate(err),
            timed_out=timed_out,
            sandbox=self.name,
        )


class DockerSandbox:
    name = "docker"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_args(self, workspace: Path, argv: list[str], needs_network: bool) -> list[str]:
        s = self.settings
        return [
            "docker",
            "run",
            "--rm",
            "--init",
            "--network",
            "bridge" if needs_network else "none",
            "--cpus",
            str(s.sandbox_cpus),
            "--memory",
            f"{s.sandbox_memory_mb}m",
            "--memory-swap",
            f"{s.sandbox_memory_mb}m",
            "--pids-limit",
            str(s.sandbox_pids_limit),
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",  # noqa: S108 - tmpfs inside the container
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/workspace",
            "--workdir",
            "/workspace",
            "--volume",
            f"{workspace}:/workspace:rw",
            s.sandbox_image,
            *argv,
        ]

    async def run(self, workspace: Path, argv: list[str], timeout: int) -> CommandResult:
        rule = validate_command(argv, allow_dependency_install=self.settings.allow_dependency_install)
        args = self.build_args(workspace.resolve(), argv, rule.needs_network)
        start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout + 15)
        except TimeoutError:
            timed_out = True
            proc.kill()
            out, err = await proc.communicate()
        if proc.returncode == 125:
            raise SandboxError(f"docker failed to start the sandbox: {err.decode(errors='replace')[:500]}")
        return CommandResult(
            argv=argv,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=int((time.perf_counter() - start) * 1000),
            stdout=_truncate(out),
            stderr=_truncate(err),
            timed_out=timed_out,
            sandbox=self.name,
        )


class RunnerSandbox:
    """Client for the sandbox-runner service. Workspaces live on a shared volume."""

    name = "runner"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self, workspace: Path, argv: list[str], timeout: int) -> CommandResult:
        validate_command(argv, allow_dependency_install=self.settings.allow_dependency_install)
        root = self.settings.workspace_root.resolve()
        rel = workspace.resolve().relative_to(root)
        headers = {}
        if self.settings.sandbox_runner_token:
            headers["Authorization"] = f"Bearer {self.settings.sandbox_runner_token.get_secret_value()}"
        async with httpx.AsyncClient(timeout=timeout + 30) as client:
            resp = await client.post(
                f"{self.settings.sandbox_runner_url}/run",
                json={"workspace": str(rel), "argv": argv, "timeout": timeout},
                headers=headers,
            )
        if resp.status_code != 200:
            raise SandboxError(f"sandbox runner returned {resp.status_code}: {resp.text[:300]}")
        return CommandResult.model_validate(resp.json())


def build_sandbox(settings: Settings) -> Sandbox:
    if settings.sandbox_mode == "docker":
        return DockerSandbox(settings)
    if settings.sandbox_mode == "runner":
        return RunnerSandbox(settings)
    return LocalSandbox(settings)
