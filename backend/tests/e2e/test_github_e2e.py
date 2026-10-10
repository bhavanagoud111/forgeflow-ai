"""Feature workflow against a GitHub repository with the GitHub API mocked."""

import io
import json
import tarfile

import httpx
import pytest
import respx
from pydantic import SecretStr

from forgeflow.api.app import create_app
from forgeflow.container import build_container
from tests.conftest import SAMPLE_REPO, make_settings, wait_for_status

API = "https://api.github.com"


def sample_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(SAMPLE_REPO.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                tar.add(path, arcname=f"octo-taskboard-abc123/{path.relative_to(SAMPLE_REPO)}")
    return buf.getvalue()


@pytest.fixture
async def gh_client(tmp_path):
    settings = make_settings(tmp_path, github_token=SecretStr("ghp_" + "t" * 36), local_repo_roots=[])
    c = await build_container(settings)
    app = create_app(settings, container=c)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer test-admin-token"},
        ) as client:
            yield client, c
    await c.close()


@respx.mock(assert_all_called=False)
async def test_feature_request_opens_draft_pull_request(gh_client, respx_mock):
    client, container = gh_client
    respx_mock.get(f"{API}/repos/octo/taskboard").respond(
        json={"full_name": "octo/taskboard", "default_branch": "main", "description": "d"}
    )
    respx_mock.get(f"{API}/repos/octo/taskboard/git/ref/heads/main").respond(json={"object": {"sha": "abc123"}})
    respx_mock.get(f"{API}/repos/octo/taskboard/tarball/abc123").respond(
        content=sample_tarball(), headers={"content-type": "application/x-gzip"}
    )
    blobs = respx_mock.post(f"{API}/repos/octo/taskboard/git/blobs").respond(201, json={"sha": "blob"})
    respx_mock.get(f"{API}/repos/octo/taskboard/git/commits/abc123").respond(json={"tree": {"sha": "t0"}})
    respx_mock.post(f"{API}/repos/octo/taskboard/git/trees").respond(201, json={"sha": "t1"})
    respx_mock.post(f"{API}/repos/octo/taskboard/git/commits").respond(201, json={"sha": "c1"})
    refs = respx_mock.post(f"{API}/repos/octo/taskboard/git/refs").respond(201, json={})
    respx_mock.get(f"{API}/repos/octo/taskboard/pulls").respond(json=[])
    pulls = respx_mock.post(f"{API}/repos/octo/taskboard/pulls").respond(
        201, json={"number": 7, "html_url": "https://github.com/octo/taskboard/pull/7"}
    )

    repo = (
        await client.post("/api/repositories/connect", json={"provider": "github", "full_name": "octo/taskboard"})
    ).json()
    r = await client.post(
        "/api/executions",
        json={
            "repository_id": repo["id"],
            "workflow": "feature",
            "request": "Add JWT authentication to this FastAPI application",
            "params": {"issue": 12},
        },
    )
    eid = r.json()["id"]
    ex = await wait_for_status(container, eid)
    assert ex.status == "awaiting_approval", ex.error
    assert not pulls.called and not refs.called  # nothing is written before approval

    detail = (await client.get(f"/api/executions/{eid}")).json()
    approval = (await client.get("/api/approvals")).json()["items"][0]
    assert approval["details"]["publish"] is True
    assert any("pull_requests:write" in p for p in approval["requested_permissions"])
    await client.post(f"/api/approvals/{detail['pending_approval_id']}/approve")
    ex = await wait_for_status(container, eid)
    assert ex.status == "succeeded", ex.error

    pr_body = json.loads(pulls.calls.last.request.content)
    assert pr_body["head"].startswith("forgeflow/") and pr_body["base"] == "main" and pr_body["draft"] is True
    assert "Refs #12" in pr_body["body"]
    assert json.loads(refs.calls.last.request.content)["ref"].startswith("refs/heads/forgeflow/")
    assert blobs.call_count >= 6
    report = (await client.get(f"/api/executions/{eid}")).json()["report"]
    assert report["pr"]["url"] == "https://github.com/octo/taskboard/pull/7" and report["pr"]["published"]
