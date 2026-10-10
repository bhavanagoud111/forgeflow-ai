"""End-to-end workflows through the HTTP API with the embedded worker.

The demo provider supplies scripted model output; everything else is real: workspaces,
patch application, sandboxed pytest runs, debugging loops, review, verification,
approval interrupts, checkpoint resume and reports.
"""

import json
import os

import pytest

from tests.conftest import sample_repo_id, wait_for_status


async def _submit(client, workflow, request, **params):
    repo = await sample_repo_id(client)
    r = await client.post(
        "/api/executions", json={"repository_id": repo, "workflow": workflow, "request": request, "params": params}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _events(client, eid):
    return (await client.get(f"/api/executions/{eid}/events/history")).json()


async def test_feature_request_end_to_end(client, container):
    eid = await _submit(client, "feature", "Add JWT authentication to this FastAPI application")
    ex = await wait_for_status(container, eid)
    assert ex.status == "awaiting_approval", ex.error

    detail = (await client.get(f"/api/executions/{eid}")).json()
    state = detail["state"]
    assert [t["task_id"] for t in state["plan"]["tasks"]] == ["TASK-001", "TASK-002", "TASK-003", "TASK-004"]
    assert state["batches"] == [["TASK-001", "TASK-002"], ["TASK-003"], ["TASK-004"]]
    assert state["debug_attempts"] == 2 and len(state["diagnoses"]) == 2
    assert state["test_run"]["passed"] is True
    assert state["verification"]["complete"] is True
    assert not any(f["severity"] == "critical" for f in state["review"]["findings"])
    assert "+++ b/taskboard/security.py" in state["diff"]
    approval_id = detail["pending_approval_id"]

    pending = (await client.get("/api/approvals", params={"status": "pending"})).json()["items"]
    assert pending[0]["id"] == approval_id and pending[0]["details"]["publish"] is False

    r = await client.post(f"/api/approvals/{approval_id}/approve", json={"comment": "ship it"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    again = await client.post(f"/api/approvals/{approval_id}/approve")
    assert again.status_code == 409

    ex = await wait_for_status(container, eid)
    assert ex.status == "succeeded", ex.error
    report = (await client.get(f"/api/executions/{eid}")).json()["report"]
    assert report["outcome"] == "succeeded" and report["pr"]["published"] is False
    assert report["test_runs"] == 3 and report["simulated"] is True
    assert {c["path"] for c in report["changed"]} >= {
        "taskboard/security.py",
        "taskboard/auth.py",
        "taskboard/main.py",
        "tests/test_auth_endpoints.py",
    }
    assert "Verification" in report["pr_draft"]["body"] and "demo provider" in report["pr_draft"]["body"]

    types = [e["type"] for e in await _events(client, eid)]
    for expected in [
        "workflow.started",
        "plan.created",
        "patch.applied",
        "test.failed",
        "test.passed",
        "review.completed",
        "verification.completed",
        "approval.required",
        "approval.decided",
        "workflow.resumed",
        "pr.created",
        "workflow.completed",
    ]:
        assert expected in types, expected
    assert types.index("test.failed") < types.index("test.passed") < types.index("approval.required")

    trace = (await client.get(f"/api/executions/{eid}/trace")).json()
    agents = {r["agent_id"] for r in trace["runs"]}
    assert agents == {
        "orchestrator",
        "repository_analyst",
        "task_planner",
        "code_generator",
        "debugger",
        "code_reviewer",
        "verifier",
        "pull_request",
    }
    assert trace["totals"]["failed_runs"] == 0 and trace["totals"]["tool_calls"] > 10
    assert any(t["tool"] == "sandbox.run" for t in trace["tool_calls"])


async def test_sse_stream_replays_and_resumes(client, container):
    eid = await _submit(client, "repo_onboarding", "")
    await wait_for_status(container, eid)

    async def read(headers=None, params=None):
        seqs, types = [], []
        async with client.stream("GET", f"/api/executions/{eid}/events", headers=headers, params=params) as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            event = None
            async for line in r.aiter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                    types.append(event)
                elif line.startswith("data:") and event != "stream.end":
                    seqs.append(json.loads(line.split(":", 1)[1])["seq"])
        return seqs, types

    seqs, types = await read()
    assert seqs == list(range(1, len(seqs) + 1)) and types[-1] == "stream.end"
    resumed, _ = await read(headers={"Last-Event-ID": "3"})
    assert resumed == seqs[3:]


async def test_bug_investigation_end_to_end(client, container):
    eid = await _submit(
        client, "bug_investigation", "PATCH /tasks/{id} with completed=false does not reopen a completed task"
    )
    ex = await wait_for_status(container, eid)
    assert ex.status == "awaiting_approval", ex.error
    state = (await client.get(f"/api/executions/{eid}")).json()["state"]
    assert "`if data.completed:`" in state["diagnoses"][0]["root_cause"]
    assert state["debug_attempts"] == 1 and state["reproduction"]["files"] == ["tests/test_regression_reopen.py"]
    assert state["test_run"]["passed"] and "+        if data.completed is not None:" in state["diff"]


async def test_test_generation_rejects_and_records_decision(client, container):
    eid = await _submit(client, "test_generation", "Add unit tests for TaskStore")
    await wait_for_status(container, eid)
    approval_id = (await client.get(f"/api/executions/{eid}")).json()["pending_approval_id"]
    r = await client.post(f"/api/approvals/{approval_id}/reject", json={"comment": "not now"})
    assert r.json()["status"] == "rejected"
    ex = await wait_for_status(container, eid, {"rejected"})
    assert "not now" in ex.summary
    repo = await sample_repo_id(client)
    history = (await client.get(f"/api/repositories/{repo}")).json()["history"]
    assert any(h["kind"] == "decision" for h in history)


async def test_code_review_of_a_diff(client, container):
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1,2 @@\n x = 1\n+subprocess.run(user_input, shell=True)\n"
    eid = await _submit(client, "code_review", "Review this change", diff=diff)
    ex = await wait_for_status(container, eid)
    assert ex.status == "succeeded"
    findings = (await client.get(f"/api/executions/{eid}")).json()["report"]["review"]["findings"]
    assert any(f["title"] == "Shell invocation" and f["line"] == 2 for f in findings)


async def test_unscripted_request_fails_honestly_in_demo_mode(client, container):
    eid = await _submit(client, "feature", "Add Redis caching to the list endpoint")
    ex = await wait_for_status(container, eid)
    assert ex.status == "failed" and "No code changes were produced" in ex.summary


async def test_cancel_awaiting_execution(client, container):
    eid = await _submit(client, "test_generation", "Add unit tests for TaskStore")
    await wait_for_status(container, eid)
    r = await client.post(f"/api/executions/{eid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    approvals = (await client.get("/api/approvals")).json()["items"]
    assert approvals[0]["status"] == "expired"
    assert (await client.post(f"/api/executions/{eid}/cancel")).status_code == 409


async def test_critical_review_finding_blocks(client, container, monkeypatch):
    from forgeflow.demo import taskboard_files as tb

    leaked = tb.TEST_STORE_PY + '\nGITHUB = "ghp_' + "A" * 36 + '"\n'
    monkeypatch.setattr(tb, "TEST_STORE_PY", leaked)
    eid = await _submit(client, "test_generation", "Add unit tests for TaskStore")
    ex = await wait_for_status(container, eid)
    assert ex.status == "blocked"
    assert (await client.get("/api/approvals", params={"status": "pending"})).json()["total"] == 0


async def test_unsafe_local_sandbox_is_refused_for_real_models(client, container, monkeypatch):
    monkeypatch.setattr(container.services.llm, "simulated", False, raising=False)
    eid = await _submit(client, "repo_onboarding", "")
    ex = await wait_for_status(container, eid)
    assert ex.status == "failed" and "local sandbox" in ex.error


@pytest.mark.skipif(os.environ.get("FORGEFLOW_TEST_DOCKER") != "1", reason="set FORGEFLOW_TEST_DOCKER=1 to run")
async def test_feature_workflow_with_docker_sandbox(tmp_path):
    from forgeflow.container import build_container
    from tests.conftest import make_settings

    settings = make_settings(tmp_path, sandbox_mode="docker")
    c = await build_container(settings)
    try:
        async with c.services.db.session() as s:
            from forgeflow.db.models import Execution, Repository
            from tests.conftest import SAMPLE_REPO

            repo = Repository(provider="local", full_name="local/taskboard-api", local_path=str(SAMPLE_REPO))
            s.add(repo)
            await s.flush()
            ex = Execution(
                workflow="feature",
                repository_id=repo.id,
                created_by="t",
                request="Add JWT authentication to this FastAPI application",
            )
            s.add(ex)
            await s.flush()
            eid = ex.id
        await c.engine.run(eid)
        state = (await c.engine.snapshot(eid, "feature"))["values"]
        assert state["test_run"]["passed"] and state["test_run"]["commands"][0]["sandbox"] == "docker"
        assert state["debug_attempts"] == 2
    finally:
        await c.close()
