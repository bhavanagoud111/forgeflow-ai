# ForgeFlow backend

FastAPI service, LangGraph workflows, agents, sandbox runner and MCP server.
See the repository [README](../README.md) and [ARCHITECTURE](../ARCHITECTURE.md).

```bash
uv sync
uv run uvicorn forgeflow.main:app --reload     # API + embedded worker
uv run forgeflow-worker                        # standalone worker
uv run forgeflow-mcp                           # MCP server (stdio), needs FORGEFLOW_MCP_TOKEN
uv run forgeflow create-token --name me --role operator
uv run pytest -q
```
