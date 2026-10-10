import os

import pytest

from forgeflow.security.command_policy import CommandRejected
from forgeflow.workspace.sandbox import DockerSandbox, LocalSandbox
from tests.conftest import make_settings


async def test_local_sandbox_runs_allowlisted_command_with_clean_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGEFLOW_GITHUB_TOKEN", "ghp_should_not_leak")
    ws = tmp_path / "w" / "repo"
    ws.mkdir(parents=True)
    (ws / "test_env.py").write_text(
        "import os\n\ndef test_env():\n    assert 'FORGEFLOW_GITHUB_TOKEN' not in os.environ\n"
        "    assert not [k for k in os.environ if 'TOKEN' in k or 'SECRET' in k or k.startswith('FORGEFLOW')]\n"
    )
    result = await LocalSandbox(make_settings(tmp_path)).run(
        ws, ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], timeout=60
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.sandbox == "local"


async def test_local_sandbox_enforces_timeout(tmp_path):
    ws = tmp_path / "w" / "repo"
    ws.mkdir(parents=True)
    (ws / "test_slow.py").write_text("import time\n\ndef test_slow():\n    time.sleep(30)\n")
    result = await LocalSandbox(make_settings(tmp_path)).run(ws, ["python", "-m", "pytest", "-q"], timeout=2)
    assert result.timed_out and result.duration_ms < 15_000


async def test_sandboxes_reject_disallowed_commands(tmp_path):
    with pytest.raises(CommandRejected):
        await LocalSandbox(make_settings(tmp_path)).run(tmp_path, ["sh", "-c", "id"], timeout=5)


def test_docker_sandbox_isolation_flags(tmp_path):
    args = DockerSandbox(make_settings(tmp_path, sandbox_memory_mb=512)).build_args(
        tmp_path, ["python", "-m", "pytest"], needs_network=False
    )
    joined = " ".join(args)
    for flag in (
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--user 65534:65534",
        "--memory 512m",
        "--pids-limit",
    ):
        assert flag in joined
    assert "--privileged" not in args and "-e" not in args
    assert not any(a.startswith(("GITHUB", "FORGEFLOW")) for a in args)
    assert f"{tmp_path}:/workspace:rw" in args


@pytest.mark.skipif(os.environ.get("FORGEFLOW_TEST_DOCKER") != "1", reason="set FORGEFLOW_TEST_DOCKER=1 to run")
async def test_docker_sandbox_has_no_network(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "test_net.py").write_text(
        "import socket, pytest\n\ndef test_no_network():\n    with pytest.raises(OSError):\n"
        "        socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
    )
    result = await DockerSandbox(make_settings(tmp_path)).run(
        ws, ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], timeout=60
    )
    assert result.exit_code == 0, result.stdout + result.stderr
