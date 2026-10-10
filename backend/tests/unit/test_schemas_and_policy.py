import pytest

from forgeflow.agents.coder import PatchRejected, check_scope
from forgeflow.schemas import FileEdit, PatchProposal, PullRequestDraft
from forgeflow.security.command_policy import CommandRejected, validate_command


@pytest.mark.parametrize("path", ["/etc/passwd", "../x.py", "a/../../b.py", ".git/config", "", "a b.py"])
def test_file_edit_rejects_unsafe_paths(path):
    with pytest.raises(ValueError):
        FileEdit(path=path, operation="create", content="x")


def test_file_edit_shape_rules():
    with pytest.raises(ValueError):
        FileEdit(path="a.py", operation="replace", search="x")
    with pytest.raises(ValueError):
        FileEdit(path="a.py", operation="create")
    assert FileEdit(path="a.py", operation="delete").operation == "delete"


@pytest.mark.parametrize(
    "path",
    [".github/workflows/ci.yml", ".env", "config/.env.local", "certs/server.pem", "uv.lock", "package-lock.json"],
)
def test_protected_paths_are_rejected(path):
    proposal = PatchProposal(
        task_id="TASK-001", summary="s", edits=[FileEdit(path=path, operation="create", content="x")]
    )
    with pytest.raises(PatchRejected):
        check_scope(proposal, max_files=10)


def test_patch_file_limit():
    edits = [FileEdit(path=f"f{i}.py", operation="create", content="x") for i in range(4)]
    with pytest.raises(PatchRejected, match="limit"):
        check_scope(PatchProposal(task_id="TASK-001", summary="s", edits=edits), max_files=3)


def test_pull_request_branch_must_be_forgeflow_namespace():
    with pytest.raises(ValueError):
        PullRequestDraft(title="Valid title", body="b", branch="main")
    assert PullRequestDraft(title="Valid title", body="b", branch="forgeflow/abc").branch == "forgeflow/abc"


@pytest.mark.parametrize(
    "argv",
    [
        ["python", "-m", "pytest", "-q"],
        ["python", "-m", "compileall", "-q", "."],
        ["npm", "test", "--", "--watch=false"],
        ["go", "test", "./..."],
    ],
)
def test_allowed_commands(argv):
    validate_command(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "-c", "ls"],
        ["python", "-c", "import os"],
        ["python", "-m", "pytest", "; rm -rf /"],
        ["python", "-m", "pytest", "/etc"],
        ["python", "-m", "pytest", "../other"],
        ["npm", "test", "--", "--watch=false", "--extra"],
        ["curl", "https://example.com"],
        [],
    ],
)
def test_rejected_commands(argv):
    with pytest.raises(CommandRejected):
        validate_command(argv)


def test_dependency_installation_is_off_by_default():
    argv = ["python", "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "-r", "requirements.txt"]
    with pytest.raises(CommandRejected, match="disabled"):
        validate_command(argv)
    assert validate_command(argv, allow_dependency_install=True).needs_network
