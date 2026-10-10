import json

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from forgeflow.integrations.github import FileChange, GitHubClient, GitHubError, GitHubNotConfigured, parse_repo
from tests.conftest import make_settings

API = "https://api.github.com"


def client(tmp_path, **kw):
    return GitHubClient(make_settings(tmp_path, github_token=SecretStr("ghp_test"), **kw))


def test_parse_repo():
    assert parse_repo("https://github.com/octo/repo.git") == "octo/repo"
    assert parse_repo("octo/repo") == "octo/repo"
    with pytest.raises(ValueError):
        parse_repo("octo/repo/extra")


async def test_unconfigured_client_is_read_only_demo(tmp_path):
    with pytest.raises(GitHubNotConfigured):
        await GitHubClient(make_settings(tmp_path)).get_repo("octo/repo")


@respx.mock
async def test_reads_repo_issues_and_ci(tmp_path):
    respx.get(f"{API}/repos/octo/repo").respond(json={"full_name": "octo/repo", "default_branch": "main"})
    respx.get(f"{API}/repos/octo/repo/issues").respond(
        json=[{"number": 1, "title": "Bug"}, {"number": 2, "title": "PR", "pull_request": {}}]
    )
    respx.get(f"{API}/repos/octo/repo/commits/abc/status").respond(
        json={"state": "success", "statuses": [{"context": "ci", "state": "success"}]}
    )
    respx.get(f"{API}/repos/octo/repo/commits/abc/check-runs").respond(
        json={"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]}
    )
    gh = client(tmp_path)
    assert (await gh.get_repo("octo/repo"))["default_branch"] == "main"
    assert [i["number"] for i in await gh.list_issues("octo/repo")] == [1]
    ci = await gh.ci_status("octo/repo", "abc")
    assert ci["state"] == "success" and ci["check_runs"][0]["conclusion"] == "success"
    assert respx.calls.last.request.headers["Authorization"] == "Bearer ghp_test"


@respx.mock
async def test_push_branch_and_create_pull(tmp_path):
    respx.post(f"{API}/repos/octo/repo/git/blobs").respond(201, json={"sha": "blob1"})
    respx.get(f"{API}/repos/octo/repo/git/commits/base").respond(json={"tree": {"sha": "basetree"}})
    trees = respx.post(f"{API}/repos/octo/repo/git/trees").respond(201, json={"sha": "tree1"})
    respx.post(f"{API}/repos/octo/repo/git/commits").respond(201, json={"sha": "commit1"})
    refs = respx.post(f"{API}/repos/octo/repo/git/refs").respond(201, json={})
    respx.get(f"{API}/repos/octo/repo/pulls").respond(json=[])
    pulls = respx.post(f"{API}/repos/octo/repo/pulls").respond(201, json={"number": 5, "html_url": "https://x/5"})
    gh = client(tmp_path)
    sha = await gh.push_branch(
        "octo/repo", "forgeflow/abc", "base", "msg", [FileChange("a.py", "x"), FileChange("old.py", None)]
    )
    assert sha == "commit1"
    tree_body = json.loads(trees.calls.last.request.content)
    assert tree_body["base_tree"] == "basetree"
    assert {"path": "old.py", "mode": "100644", "type": "blob", "sha": None} in tree_body["tree"]
    assert json.loads(refs.calls.last.request.content)["ref"] == "refs/heads/forgeflow/abc"
    pr = await gh.create_pull("octo/repo", head="forgeflow/abc", base="main", title="t", body="b")
    assert pr["number"] == 5 and json.loads(pulls.calls.last.request.content)["draft"] is True


@respx.mock
async def test_push_is_idempotent_and_never_forces(tmp_path):
    respx.post(f"{API}/repos/octo/repo/git/blobs").respond(201, json={"sha": "blob1"})
    respx.get(f"{API}/repos/octo/repo/git/commits/base").respond(json={"tree": {"sha": "basetree"}})
    respx.post(f"{API}/repos/octo/repo/git/trees").respond(201, json={"sha": "tree1"})
    respx.post(f"{API}/repos/octo/repo/git/commits").respond(201, json={"sha": "commit2"})
    respx.post(f"{API}/repos/octo/repo/git/refs").respond(422, json={"message": "Reference already exists"})
    respx.get(f"{API}/repos/octo/repo/git/ref/heads/forgeflow/abc").respond(json={"object": {"sha": "commit1"}})
    head = respx.get(f"{API}/repos/octo/repo/git/commits/commit1").respond(json={"tree": {"sha": "tree1"}})
    patch = respx.patch(url__regex=r".*/git/refs/.*").respond(200, json={})
    gh = client(tmp_path)
    assert await gh.push_branch("octo/repo", "forgeflow/abc", "base", "m", [FileChange("a.py", "x")]) == "commit1"
    head.respond(json={"tree": {"sha": "different"}})
    with pytest.raises(GitHubError, match="different content"):
        await gh.push_branch("octo/repo", "forgeflow/abc", "base", "m", [FileChange("a.py", "x")])
    assert not patch.called


async def test_refuses_branches_outside_namespace(tmp_path):
    with pytest.raises(GitHubError, match="forgeflow"):
        await client(tmp_path).push_branch("octo/repo", "main", "base", "m", [])


@respx.mock
async def test_create_pull_returns_existing(tmp_path):
    respx.get(f"{API}/repos/octo/repo/pulls").respond(json=[{"number": 3, "html_url": "u"}])
    post = respx.post(f"{API}/repos/octo/repo/pulls")
    pr = await client(tmp_path).create_pull("octo/repo", head="forgeflow/x", base="main", title="t", body="b")
    assert pr["number"] == 3 and not post.called


@respx.mock
async def test_github_app_installation_token(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    settings = make_settings(
        tmp_path, github_app_id="123", github_app_private_key=SecretStr(pem), github_app_installation_id="9"
    )
    mint = respx.post(f"{API}/app/installations/9/access_tokens").respond(201, json={"token": "ghs_inst"})
    repo = respx.get(f"{API}/repos/octo/repo").respond(json={"full_name": "octo/repo"})
    gh = GitHubClient(settings)
    await gh.get_repo("octo/repo")
    await gh.get_repo("octo/repo")
    assert mint.call_count == 1  # cached
    app_jwt = mint.calls.last.request.headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(app_jwt, key.public_key(), algorithms=["RS256"])
    assert claims["iss"] == "123"
    assert repo.calls.last.request.headers["Authorization"] == "Bearer ghs_inst"


@respx.mock
async def test_errors_carry_status(tmp_path):
    respx.get(f"{API}/repos/octo/missing").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(GitHubError) as info:
        await client(tmp_path).get_repo("octo/missing")
    assert info.value.status == 404
