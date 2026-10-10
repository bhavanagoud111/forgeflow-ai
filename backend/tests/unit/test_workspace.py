import io
import os
import tarfile

import pytest

from forgeflow.schemas import FileEdit
from forgeflow.workspace.manager import EditError, WorkspaceManager


@pytest.fixture
async def ws(tmp_path):
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "a.py").write_text("x = 1\ny = 2\n")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "big.js").write_text("ignored")
    os.symlink("/etc/hosts", src / "link")
    mgr = WorkspaceManager(tmp_path / "workspaces")
    return mgr, await mgr.create_from_local("exec_test", src, "forgeflow/test")


async def test_workspace_is_a_clean_copy_on_a_forgeflow_branch(ws):
    mgr, w = ws
    assert (w.path / "pkg" / "a.py").exists()
    assert not (w.path / "node_modules").exists() and not (w.path / "link").exists()
    assert (await mgr.git(w, "rev-parse", "--abbrev-ref", "HEAD")).strip() == "forgeflow/test"
    assert await mgr.diff(w) == ""


async def test_apply_edits_and_diff(ws):
    mgr, w = ws
    files = mgr.apply_edits(
        w,
        [
            FileEdit(path="pkg/a.py", operation="replace", search="y = 2\n", replacement="y = 3\n"),
            FileEdit(path="pkg/b.py", operation="create", content="z = 1\n"),
        ],
    )
    assert files == ["pkg/a.py", "pkg/b.py"]
    diff = await mgr.diff(w)
    assert "+y = 3" in diff and "+z = 1" in diff
    changed = {c["path"]: c["status"] for c in await mgr.changed_files(w)}
    assert changed == {"pkg/a.py": "modified", "pkg/b.py": "added"}


async def test_apply_edits_is_atomic(ws):
    mgr, w = ws
    with pytest.raises(EditError, match="matched 0 times"):
        mgr.apply_edits(
            w,
            [
                FileEdit(path="pkg/new.py", operation="create", content="ok\n"),
                FileEdit(path="pkg/a.py", operation="replace", search="nope", replacement="x"),
            ],
        )
    assert not (w.path / "pkg" / "new.py").exists()


async def test_ambiguous_replace_and_existing_create_fail(ws):
    mgr, w = ws
    (w.path / "pkg" / "dup.py").write_text("a\na\n")
    with pytest.raises(EditError, match="2 times"):
        mgr.apply_edits(w, [FileEdit(path="pkg/dup.py", operation="replace", search="a\n", replacement="b\n")])
    with pytest.raises(EditError, match="already exists"):
        mgr.apply_edits(w, [FileEdit(path="pkg/a.py", operation="create", content="")])


async def test_symlink_escape_is_blocked(ws, tmp_path):
    mgr, w = ws
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, w.path / "escape")
    with pytest.raises(EditError, match="escapes"):
        mgr.apply_edits(w, [FileEdit(path="escape/evil.py", operation="create", content="x")])


async def test_tarball_extraction_skips_traversal_and_links(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:

        def add(name, data=b"x", kind=tarfile.REGTYPE, link=""):
            info = tarfile.TarInfo(name)
            info.type, info.linkname, info.size = kind, link, len(data) if kind == tarfile.REGTYPE else 0
            tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)

        add("repo-abc/ok.py", b"print(1)\n")
        add("repo-abc/../../evil.py")
        add("repo-abc/link", kind=tarfile.SYMTYPE, link="/etc/passwd")
    mgr = WorkspaceManager(tmp_path / "ws")
    w = await mgr.create_from_tarball("exec_tar", buf.getvalue(), "forgeflow/t")
    assert (w.path / "ok.py").read_text() == "print(1)\n"
    assert not (w.path / "link").exists()
    assert not (tmp_path / "evil.py").exists() and not (tmp_path / "ws" / "evil.py").exists()


async def test_build_artifacts_never_enter_the_diff(ws):
    mgr, w = ws
    (w.path / "pkg" / "__pycache__").mkdir()
    (w.path / "pkg" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0binary")
    (w.path / ".pytest_cache").mkdir()
    (w.path / ".pytest_cache" / "x").write_text("cache")
    assert await mgr.changed_files(w) == []
