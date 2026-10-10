"""Workflow state survives a process restart: pause for approval in one container, resume in another."""

from sqlalchemy import select

from forgeflow.container import build_container
from forgeflow.db.models import AgentRun, Approval, Execution, Repository
from tests.conftest import SAMPLE_REPO


async def _repo_and_execution(c):
    async with c.services.db.session() as s:
        repo = Repository(provider="local", full_name="local/taskboard-api", local_path=str(SAMPLE_REPO))
        s.add(repo)
        await s.flush()
        ex = Execution(
            workflow="test_generation", repository_id=repo.id, request="Add tests for TaskStore", created_by="test"
        )
        s.add(ex)
        await s.flush()
        return ex.id


async def test_checkpoint_resume_across_containers(settings):
    first = await build_container(settings)
    eid = await _repo_and_execution(first)
    await first.engine.run(eid)
    async with first.services.db.session() as s:
        assert (await s.get(Execution, eid)).status == "awaiting_approval"
        approval = await s.scalar(select(Approval).where(Approval.execution_id == eid))
    snap = await first.engine.snapshot(eid, "test_generation")
    assert snap["next"] == ["request_approval"]
    await first.close()

    second = await build_container(settings)  # fresh process: new engine, same DB + checkpoints
    try:
        async with second.services.db.session() as s:
            ex = await s.get(Execution, eid)
            ex.status, ex.resume_payload = "resuming", {"decision": "approved", "by": "tester", "comment": None}
        await second.engine.run(eid)
        async with second.services.db.session() as s:
            ex = await s.get(Execution, eid)
            runs = list(await s.scalars(select(AgentRun.node).where(AgentRun.execution_id == eid)))
        assert ex.status == "succeeded", ex.error
        assert ex.report["pr"]["published"] is False
        assert ex.report["approval"]["id"] == approval.id
        # Nodes before the interrupt were not re-run after resume.
        assert runs.count("plan") == 1 and runs.count("create_pr") == 1
    finally:
        await second.close()
