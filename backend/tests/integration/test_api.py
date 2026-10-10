from tests.conftest import OPERATOR, VIEWER, sample_repo_id, wait_for_status


async def test_health_is_public_and_reports_demo_mode(client):
    r = await client.get("/api/health", headers={"Authorization": ""})
    assert r.status_code == 200 and r.json()["simulated_llm"] is True


async def test_authentication_and_roles(client):
    assert (await client.get("/api/executions", headers={"Authorization": ""})).json()["error"][
        "code"
    ] == "unauthorized"
    assert (await client.get("/api/executions", headers={"Authorization": "Bearer nope"})).status_code == 401
    repo = await sample_repo_id(client)
    body = {"repository_id": repo, "workflow": "repo_onboarding"}
    viewer = await client.post("/api/executions", json=body, headers={"Authorization": f"Bearer {VIEWER}"})
    assert viewer.status_code == 403 and viewer.json()["error"]["code"] == "forbidden"
    op = await client.post("/api/executions", json=body, headers={"Authorization": f"Bearer {OPERATOR}"})
    assert op.status_code == 201
    assert (await client.get("/api/audit", headers={"Authorization": f"Bearer {OPERATOR}"})).status_code == 403
    assert (await client.get("/api/me")).json()["role"] == "admin"


async def test_structured_validation_errors(client):
    r = await client.post("/api/executions", json={"repository_id": "x", "workflow": "nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    repo = await sample_repo_id(client)
    r = await client.post("/api/executions", json={"repository_id": repo, "workflow": "feature", "request": "hi"})
    assert r.status_code == 422
    r = await client.post(
        "/api/executions",
        json={"repository_id": repo, "workflow": "feature", "request": "Add things", "params": {"shell": "rm"}},
    )
    assert r.status_code == 422 and "Unknown params" in r.json()["error"]["message"]
    r = await client.post("/api/executions", json={"repository_id": repo, "workflow": "code_review"})
    assert r.status_code == 422


async def test_local_repository_connection_is_restricted(client, tmp_path):
    r = await client.post("/api/repositories/connect", json={"provider": "local", "path": str(tmp_path)})
    assert r.status_code == 403
    r = await client.post("/api/repositories/connect", json={"provider": "github", "full_name": "octo/repo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "github_not_configured"


async def test_pagination_and_filters(client, container):
    repo = await sample_repo_id(client)
    ids = []
    for _ in range(3):
        r = await client.post("/api/executions", json={"repository_id": repo, "workflow": "repo_onboarding"})
        ids.append(r.json()["id"])
    for eid in ids:
        await wait_for_status(container, eid)
    page = (await client.get("/api/executions", params={"limit": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    done = (await client.get("/api/executions", params={"status": "succeeded"})).json()
    assert done["total"] == 3


async def test_repository_endpoints(client, container):
    repo = await sample_repo_id(client)
    r = await client.post(f"/api/repositories/{repo}/analyze")
    assert r.status_code == 202
    await wait_for_status(container, r.json()["id"])
    detail = (await client.get(f"/api/repositories/{repo}")).json()
    assert "FastAPI" in detail["analysis"]["frameworks"]
    assert set(detail["memory"]) == {"architecture", "conventions", "dependencies", "test_structure", "modules"}
    tree = (await client.get(f"/api/repositories/{repo}/tree")).json()
    assert "taskboard/store.py" in tree["files"]
    f = (await client.get(f"/api/repositories/{repo}/files", params={"path": "taskboard/store.py"})).json()
    assert "class TaskStore" in f["content"]
    assert (await client.get(f"/api/repositories/{repo}/files", params={"path": "../secrets"})).status_code == 422
    issues = (await client.get(f"/api/repositories/{repo}/issues")).json()
    assert issues["items"] == [] and "GitHub" in issues["note"]
    assert (await client.delete(f"/api/repositories/{repo}/memory")).status_code == 204
    assert (await client.get(f"/api/repositories/{repo}")).json()["memory"] == {}


async def test_metrics_agents_workflows_settings(client):
    metrics = (await client.get("/api/metrics")).json()
    assert {"executions", "avg_duration_ms", "pending_approvals", "repositories", "usage", "daily"} <= set(metrics)
    agents = (await client.get("/api/agents")).json()
    assert len(agents) == 8 and {a["state"] for a in agents} <= {"idle", "active", "error"}
    workflows = (await client.get("/api/workflows")).json()
    assert {w["id"] for w in workflows} == {
        "feature",
        "bug_investigation",
        "code_review",
        "repo_onboarding",
        "test_generation",
    }
    settings = (await client.get("/api/settings")).text
    assert "test-admin-token" not in settings


async def test_rate_limiting(client):
    client._transport.app.state.rate_limiter.per_minute = 3  # type: ignore[attr-defined]
    codes = [(await client.get("/api/me")).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429
