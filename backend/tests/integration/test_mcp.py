import json

from mcp.client.client import Client
from sqlalchemy import select

from forgeflow.db.models import Repository, User
from forgeflow.mcp_server import build_mcp_server
from tests.conftest import SAMPLE_REPO


async def _setup(container, role):
    async with container.services.db.session() as s:
        s.add(Repository(provider="local", full_name="local/taskboard-api", local_path=str(SAMPLE_REPO)))
        user = await s.scalar(select(User).where(User.role == role))
    return user


def _payload(result):
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data) if isinstance(data, dict) else data
    return json.loads(result.content[0].text)


async def test_mcp_tools_list_search_and_start(container):
    user = await _setup(container, "operator")
    server = build_mcp_server(container, user)
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {
            "list_repositories",
            "search_repository",
            "get_execution",
            "list_executions",
            "start_execution",
        }
        repos = _payload(await client.call_tool("list_repositories", {}))
        repo_id = repos[0]["id"]
        hits = _payload(
            await client.call_tool("search_repository", {"repository_id": repo_id, "query": "update completed"})
        )
        assert hits[0]["path"] == "taskboard/store.py"
        started = _payload(
            await client.call_tool(
                "start_execution", {"repository_id": repo_id, "workflow": "repo_onboarding", "request": "Analyse"}
            )
        )
        assert started["status"] == "queued"
        got = _payload(await client.call_tool("get_execution", {"execution_id": started["id"]}))
        assert got["workflow"] == "repo_onboarding"


async def test_mcp_viewer_cannot_start(container):
    user = await _setup(container, "viewer")
    async with Client(build_mcp_server(container, user)) as client:
        repo_id = _payload(await client.call_tool("list_repositories", {}))[0]["id"]
        result = await client.call_tool(
            "start_execution", {"repository_id": repo_id, "workflow": "feature", "request": "Add things"}
        )
        assert result.is_error
