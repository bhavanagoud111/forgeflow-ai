# ForgeFlow AI

**From issue to pull request, powered by coordinated AI agents.**

ForgeFlow AI is a multi-agent software delivery platform. Given a repository and a request such
as *"Add JWT authentication to this FastAPI application"*, it analyses the codebase, plans
dependent tasks, generates changes in parallel inside an isolated workspace, runs the tests in a
sandbox, debugs failures within a fixed attempt budget, reviews and verifies the result, and asks
a human before opening a pull request.

Every stage is visible: live events, agent runs, tool calls, token usage, diffs, test output and
review findings are stored and streamed to the UI. ForgeFlow never reports success without running
the checks that prove it.

![ForgeFlow AI: a feature request goes from plan to parallel code generation, sandboxed tests, two debugging rounds, review, human approval and a prepared pull request](docs/media/forgeflow-demo.gif)

<sub>42-second walkthrough recorded from the running app (demo provider, real sandboxed test runs).
Full-quality video: [`docs/media/forgeflow-demo.mp4`](docs/media/forgeflow-demo.mp4).</sub>

### At a glance

| | |
| --- | --- |
| **Input** | A repository plus a request, a GitHub issue, a bug report or a pull request |
| **Output** | A verified branch with a draft pull request, a review report, or a diagnosis, with every step recorded |
| **Guardrails** | Sandboxed execution, allowlisted commands, bounded retries, and human approval before anything leaves the system |
| **Try it** | `make setup && make api` + `make web`, no API keys needed ([demo mode](#demo-mode)) |

---

## Contents

1. [Screenshots](#screenshots)
1. [Adopting ForgeFlow in your organization](#adopting-forgeflow-in-your-organization)
1. [Capabilities](#capabilities)
2. [Architecture](#architecture)
3. [Agents](#agents)
4. [LangGraph workflows](#langgraph-workflows)
5. [Technology stack](#technology-stack)
6. [Installation](#installation)
7. [Configuration](#environment-variables)
8. [Local development](#local-development)
9. [Docker](#docker)
10. [GitHub integration](#github-integration)
11. [Slack integration](#slack-integration)
12. [Example workflows](#example-workflows)
13. [Testing](#testing)
14. [Security](#security)
15. [Known limitations](#known-limitations)
16. [Roadmap](#roadmap)

## Screenshots

All screenshots are from the running application with data produced by real executions.

| Dashboard | Agent Control Center |
| --- | --- |
| ![Dashboard](docs/media/01-dashboard.png) | ![Agents](docs/media/02-agents.png) |
| **Live workflow graph** with per-node agent runs and tool calls | **Plan**: tasks, dependencies, parallel batches, acceptance criteria |
| ![Workflow graph](docs/media/04-workflow-graph.png) | ![Plan](docs/media/05-plan.png) |
| **Diff viewer** (side by side or unified) | **Tests and debugging**: real pytest output per attempt |
| ![Diff](docs/media/07-diff-split.png) | ![Tests](docs/media/08-tests-debugging.png) |
| **Approval Center**: files, verification, requested permissions | **Trace**: every agent run with duration, model, tokens, cost |
| ![Approvals](docs/media/13-approvals.png) | ![Trace](docs/media/12-trace.png) |

<details>
<summary>More screenshots</summary>

| | |
| --- | --- |
| Executions | ![Executions](docs/media/03-executions.png) |
| Live console | ![Console](docs/media/06-console.png) |
| Code review findings | ![Review](docs/media/09-review.png) |
| Acceptance criteria verification | ![Verification](docs/media/10-verification.png) |
| Pull request draft | ![Pull request](docs/media/11-pull-request.png) |
| Bug investigation workflow | ![Bug investigation](docs/media/14-bug-investigation.png) |
| Automated code review of a diff | ![Code review](docs/media/15-code-review.png) |
| Repository workspace and memory | ![Repository](docs/media/16-repository.png) |
| Settings | ![Settings](docs/media/17-settings.png) |

</details>

## Adopting ForgeFlow in your organization

ForgeFlow is designed to sit next to tools a team already uses rather than replace them.

| Your existing tool | How ForgeFlow plugs in |
| --- | --- |
| **GitHub** | Install a GitHub App (or fine-grained token) on selected repositories. ForgeFlow reads issues, PRs and CI status, and opens **draft** PRs on `forgeflow/*` branches only after approval, so your normal review and branch protection still apply. |
| **Slack** | `/forgeflow plan issue-42`, `/forgeflow review pull-request-17`, `/forgeflow status ...` from the channels where work is discussed, with Slack users mapped to ForgeFlow roles. |
| **IDEs and AI assistants** | The MCP server exposes repositories, executions and workflow start to any MCP-compatible client. |
| **Your LLM vendor** | Anthropic, OpenAI or a self-hosted Ollama model through one setting. Teams with strict data rules can keep inference on their own hardware. |
| **Your toolchain** | Verification commands are detected per repository (pytest, npm test/lint/typecheck, go test/vet). Build a sandbox image with your toolchain and point `FORGEFLOW_SANDBOX_IMAGE` at it. |
| **Your infrastructure** | Docker Compose today; the API, worker and sandbox runner are separate stateless services backed by Postgres and Redis, so they map directly onto Kubernetes deployments. |
| **Your observability stack** | OpenTelemetry export to Datadog, Honeycomb, Grafana Tempo or Jaeger; optional LangSmith for model calls. |

Typical use cases:

- **Backlog chores from issues**: small features, endpoint additions, config changes, turned into reviewed draft PRs.
- **Bug triage**: reproduce a report with a failing regression test before anyone touches the fix.
- **PR review assistant**: static security rules plus model review on every pull request, posted to Slack.
- **Test coverage**: generate tests for under-tested modules, with only test files allowed to change.
- **Onboarding**: architecture, conventions and test structure summaries stored as repository memory.

Rollout suggestion: start with `repo_onboarding` and `code_review` (read-only), then enable
`test_generation`, then feature and bug workflows on low-risk repositories, keeping the
approval gate on throughout. See [Known limitations](#known-limitations) before production use.

## Capabilities

| Capability | Status |
| --- | --- |
| Five LangGraph workflows: feature, bug investigation, code review, repository onboarding, test generation | Implemented |
| Eight specialised agents with typed, validated outputs | Implemented |
| Parallel code generation for independent tasks (`Send` fan-out per dependency batch) | Implemented |
| Isolated workspace per execution on a `forgeflow/<id>` branch | Implemented |
| Sandboxed test/lint execution: Docker per command, or a network-isolated runner service | Implemented |
| Bounded debugging loop with failure memory | Implemented |
| Static + model code review; critical findings block progression | Implemented |
| Human approval gate (LangGraph `interrupt`) before any external write | Implemented |
| GitHub: repository, issues, PRs, branches, CI status, tarball checkout, branch + draft PR creation | Implemented (tested against a mocked GitHub API) |
| Persistent checkpoints (SQLite or Postgres), resume across processes, retry from checkpoint | Implemented |
| Live events over SSE with resume (`Last-Event-ID`) | Implemented |
| Execution, repository and historical memory with retention and deletion | Implemented |
| Agent runs, tool calls, tokens, cost estimates, OpenTelemetry spans | Implemented |
| Slack `/forgeflow` commands with signature verification and role mapping | Implemented (tested with signed requests) |
| MCP server (stdio) exposing repositories, executions and workflow start | Implemented |
| Deterministic offline demo provider | Implemented, clearly labelled as simulated |
| Web dashboard: agents, workflow graph, console, diff viewer, approvals, repositories, settings | Implemented |
| Semantic (embedding) retrieval with pgvector | Not implemented; lexical BM25 retrieval is used ([why](ARCHITECTURE.md#memory)) |

## Architecture

```mermaid
flowchart LR
    UI[Web UI] -->|proxy: REST + SSE| API[FastAPI]
    Slack[Slack] -->|signed requests| API
    MCPc[MCP client] --> MCP[MCP server]
    API --> DB[(Postgres / SQLite)]
    MCP --> DB
    Worker[Worker: LangGraph engine] --> DB
    Worker --> CP[(Checkpoints)]
    Worker --> Sandbox[Sandbox: no network,<br/>no credentials]
    Worker -->|after approval| GitHub[(GitHub)]
    Worker --> LLM[(LLM via LangChain<br/>or demo provider)]
```

The API only records work; workers claim executions from the database and run the graphs, so an
execution can pause for approval in one process and resume in another. Details, sequence
diagrams and the memory/observability model are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Agents

| Agent | Responsibility | Output |
| --- | --- | --- |
| **Engineering Orchestrator** | Creates the workspace, resolves task dependencies into parallel batches, dispatches work, enforces limits, cancellation and timeouts, writes the final report | dependency batches, report |
| **Repository Analyst** | Static analysis (languages, frameworks, modules, import graph, tests, docs, entrypoints), BM25 retrieval, repository memory | `RepositoryAnalysis`, `RepositorySummary` |
| **Task Planning Agent** | Plan with tasks, dependencies, priorities, acceptance criteria, target files, risks | `ImplementationPlan` |
| **Code Generation Agent** | Focused edits for one task (`replace`/`create`/`rewrite`/`delete`), validated and applied atomically | `PatchProposal` |
| **Debugging Agent** | Root cause from failing output and relevant files, smallest corrective patch, or an explicit give-up | `Diagnosis` |
| **Code Review Agent** | Static rules (secrets, shell/eval, TLS off, CI edits, deleted tests, injection text) plus model review with severities | `ReviewReport` |
| **Verification Agent** | Runs allowlisted tests and linters in the sandbox; checks each acceptance criterion | `TestRun`, `VerificationReport` |
| **Pull Request Agent** | Title and overview from the model; verification, review and limitations sections from recorded results; branch + draft PR after approval | `PRNarrative`, PR |

## LangGraph workflows

```mermaid
flowchart TD
    A[Repository analysis] --> B[Task planning]
    B --> C[Dependency resolution]
    C --> D[Parallel code generation]
    D --> E[Test execution]
    E -->|failure| F[Debugging agent]
    F -->|bounded retry| E
    E -->|pass| G[Code review]
    G --> H[Verification]
    H --> I{{Human approval}}
    I -->|approved| J[GitHub pull request]
    I -->|rejected| K[Report]
    J --> K[Final execution report]
```

Typed state, conditional edges, persistent checkpoints, `Send`-based parallelism, retry
policies, cancellation, timeouts and `interrupt()`-based approval are described in
[ARCHITECTURE.md](ARCHITECTURE.md#workflows).

## Technology stack

| Area | Choice | Why |
| --- | --- | --- |
| API | FastAPI, Pydantic v2 | Typed request/response models and OpenAPI docs |
| Orchestration | LangGraph | Graph state, `Send` fan-out, checkpoints, interrupts |
| Models | LangChain `init_chat_model` + structured output | Provider-independent (Anthropic, OpenAI, Ollama); default `claude-opus-5-5` |
| Persistence | SQLAlchemy 2 (async), Alembic, PostgreSQL or SQLite | Same code for local dev and production |
| Rate limiting | Redis (optional; in-memory fallback) | Shared limits across API replicas |
| Sandbox | Docker | Network-less, credential-less, resource-limited execution |
| Tools protocol | MCP Python SDK | Expose ForgeFlow to IDEs and assistants |
| Observability | OpenTelemetry, optional LangSmith | Spans per agent run and tool call |
| UI | Next.js, TypeScript, Tailwind CSS, shadcn/ui-style components, React Flow, TanStack Query, Recharts | Dashboard, workflow graph, live console |
| CI | GitHub Actions | Lint, types, tests, sandbox isolation tests, dependency audit, secret scan |

## Installation

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, Docker (optional for
local dev; required for the container sandbox and Compose).

```bash
git clone <this repository> forgeflow-ai && cd forgeflow-ai
make setup
```

## Environment variables

All backend settings use the `FORGEFLOW_` prefix. The full list with comments is in
[`.env.example`](.env.example); the most important ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FORGEFLOW_ADMIN_TOKEN` | – | Bootstrap admin API token (stored hashed) |
| `FORGEFLOW_LLM_PROVIDER` | `demo` | `demo`, `anthropic`, `openai`, `ollama` |
| `FORGEFLOW_LLM_MODEL` | `claude-opus-5-5` | Model id for the provider |
| `FORGEFLOW_LLM_API_KEY` | – | Provider API key |
| `FORGEFLOW_SANDBOX_MODE` | `local` | `docker`, `runner` or `local` (tests/demo only) |
| `FORGEFLOW_DATABASE_URL` | SQLite file | `postgresql+asyncpg://...` in production |
| `FORGEFLOW_CHECKPOINT_URL` | SQLite file | `postgresql://...` in production |
| `FORGEFLOW_GITHUB_TOKEN` or `FORGEFLOW_GITHUB_APP_*` | – | Enables GitHub; read-only demo mode without it |
| `FORGEFLOW_SLACK_SIGNING_SECRET`, `FORGEFLOW_SLACK_USER_ROLES` | – | Enables Slack commands |
| `FORGEFLOW_MAX_DEBUG_ATTEMPTS` | `2` | Debugging loop limit |
| `FORGEFLOW_EXECUTION_TIMEOUT_SECONDS` / `FORGEFLOW_NODE_TIMEOUT_SECONDS` | `1800` / `600` | Timeouts |

The web app needs `FORGEFLOW_API_URL` and `FORGEFLOW_API_TOKEN` (server-side only; see
[`apps/web/.env.example`](apps/web/.env.example)).

## Local development

```bash
# Terminal 1: API + embedded worker, demo provider, local sandbox
export FORGEFLOW_ADMIN_TOKEN=dev-admin-token
make api                      # http://localhost:8000/docs

# Terminal 2: web UI
cp apps/web/.env.example apps/web/.env.local   # set FORGEFLOW_API_TOKEN=dev-admin-token
make web                      # http://localhost:3000
```

The bundled sample repository `examples/sample-repos/taskboard-api` is registered automatically
in development. To use real models, install a provider extra and switch the sandbox:

```bash
cd backend && uv sync --extra anthropic
make sandbox-image
export FORGEFLOW_LLM_PROVIDER=anthropic FORGEFLOW_LLM_API_KEY=... FORGEFLOW_SANDBOX_MODE=docker
```

ForgeFlow refuses to run model-generated code in the local sandbox unless
`FORGEFLOW_ALLOW_UNSAFE_LOCAL_SANDBOX=true` is set.

Create additional users: `make token NAME=alice ROLE=operator` (roles: viewer, operator, admin).

### Demo mode

`FORGEFLOW_LLM_PROVIDER=demo` (the default) makes every model call deterministic and offline.
Responses are either derived mechanically from real analysis data or come from scripted
scenarios for the sample repository. Everything downstream is real: edits are applied in a
workspace, `pytest` runs in the sandbox, failures feed the debugger, and the review, verification
and approval steps run as normal. Executions and PR descriptions are marked as simulated, token
usage is recorded as zero, and requests without a scripted scenario fail with an explicit
"no code changes were produced" result instead of fabricated output.

Scripted scenarios on `local/taskboard-api`:

| Workflow | Request | What happens |
| --- | --- | --- |
| Feature | "Add JWT authentication to this FastAPI application" | 4 tasks in 3 batches; the first patch has two real bugs, tests fail (9 then 1), two debug attempts fix them, 15 tests pass |
| Bug investigation | "PATCH /tasks/{id} with completed=false does not reopen a task" | A regression test reproduces the bug (fails), the debugger fixes `TaskStore.update`, tests pass |
| Test generation | "Add tests for TaskStore" | Adds `tests/test_store.py`; only test files may change |
| Onboarding | – | Analysis and repository memory (no scripting needed) |
| Code review | any diff | Static rules run for real; model review is heuristic in demo mode |

## Docker

```bash
cp .env.example .env    # set FORGEFLOW_ADMIN_TOKEN and FORGEFLOW_RUNNER_TOKEN
docker compose up --build
```

| Service | Role |
| --- | --- |
| `postgres` | Application data and LangGraph checkpoints |
| `redis` | Rate limiting |
| `api` | FastAPI; runs `alembic upgrade head` on start |
| `worker` | Executes workflows; reaches the runner over an internal network |
| `sandbox-runner` | Runs allowlisted commands; internal-only network, read-only root, no capabilities, no credentials, 1 CPU / 1 GB / 256 PIDs |
| `web` | Next.js UI on port 3000 |

## GitHub integration

1. Create a fine-grained token (or GitHub App) for the target repositories with Contents
   read/write, Pull requests read/write, Issues read, Checks/Commit statuses read.
2. Set `FORGEFLOW_GITHUB_TOKEN` (or `FORGEFLOW_GITHUB_APP_ID`, `FORGEFLOW_GITHUB_APP_PRIVATE_KEY`,
   `FORGEFLOW_GITHUB_APP_INSTALLATION_ID`).
3. Connect a repository in the UI or `POST /api/repositories/connect {"provider":"github","full_name":"owner/repo"}`.

Workspaces are created from a tarball of the base branch's current commit. After approval the
Pull Request agent creates blobs, a tree and a commit with the Git Data API, creates
`refs/heads/forgeflow/<id>`, and opens a **draft** pull request. It never pushes to the base
branch and never force-updates a branch. Without credentials, GitHub features return a clear
"read-only demo mode" message and local repositories get a locally prepared (unpublished) PR.

## Slack integration

Create a Slack app with a slash command `/forgeflow` pointing to
`https://<host>/api/slack/commands` (and optionally Events to `/api/slack/events`), then set
`FORGEFLOW_SLACK_SIGNING_SECRET`, `FORGEFLOW_SLACK_BOT_TOKEN` and the user-to-role map:

```bash
FORGEFLOW_SLACK_USER_ROLES='{"U012ABCDEF":"operator","U034GHIJKL":"viewer"}'
```

```
/forgeflow analyze owner/repository
/forgeflow plan issue-42 owner/repository
/forgeflow review pull-request-17 owner/repository
/forgeflow status execution-0123456789abcdef
```

Requests are rejected unless the HMAC signature and timestamp are valid; users not in the role
map are denied; retries are de-duplicated; free-text mentions only return help. Progress
(approval needed, final outcome) is posted back to the command's `response_url`.

## Example workflows

With the API running (`FORGEFLOW_TOKEN` = your token):

```bash
./examples/api/demo.sh          # JWT feature request: submit, wait, approve, print trace totals
```

More requests (bug investigation, PR review, SSE, approvals) are in
[`examples/api/requests.http`](examples/api/requests.http). The MCP server can be added to an
MCP client as a stdio server: `uv run --directory backend forgeflow-mcp` with
`FORGEFLOW_MCP_TOKEN` set.

## Testing

```bash
make test          # backend: unit + integration + e2e (pytest); web: vitest
make test-docker   # sandbox isolation and a full workflow using Docker containers
make lint typecheck
```

| Suite | Covers |
| --- | --- |
| `tests/unit` | dependency resolution, plan/edit/branch validation, command allowlist, redaction, routing and state transitions, static review rules, workspace edits and tarball safety, indexing/retrieval, Slack parsing and signatures |
| `tests/integration` | GitHub client (mocked HTTP, App tokens, idempotent pushes), checkpoint resume across containers, memory and event storage, local/Docker sandboxes, API auth/roles/validation/pagination/rate limits, Slack endpoints, MCP tools |
| `tests/e2e` | Every workflow through the HTTP API with the embedded worker; SSE replay/resume; approval, rejection, cancellation, blocking review findings; GitHub feature flow ending in a (mocked) draft PR; Docker-sandbox feature flow |

External services are mocked in tests; tests never call real GitHub, Slack or model APIs.

## Security

See [SECURITY.md](SECURITY.md) for the threat model. In short: untrusted content is treated as
data; models never choose commands; generated code runs only in sandboxes without network or
credentials; every external write needs a recorded human approval; secrets are redacted from
logs, events and memory.

## Known limitations

- **Demo provider**: only the scripted scenarios on the sample repository produce code without a
  real model. Its review and acceptance-criteria checks are heuristic.
- **Real-model quality** depends on the configured model; the workflows have been exercised
  end to end with the demo provider and mocked GitHub, not benchmarked against real models.
- **Toolchains**: the sandbox image ships Python tooling. JavaScript/Go repositories need a sandbox
  image with those toolchains; dependency installation is disabled by default.
- **GitHub** integration is verified against a mocked API in tests; it has not been run against
  a live repository in this codebase's CI.
- **Slack** progress updates use `response_url` (valid for 30 minutes); longer executions should
  be followed in the UI.
- **Single-tenant**: roles are global; there is no per-repository authorization yet.
- **Retrieval** is lexical; very large monorepos may need semantic retrieval.

## Roadmap

- Per-repository permissions and OAuth sign-in for the UI.
- Semantic retrieval (pgvector) behind the existing retriever interface.
- Polyglot sandbox images and opt-in dependency installation with a package mirror.
- Posting code-review findings as GitHub review comments (approval-gated).
- CI status polling after PR creation, feeding failures back into the debugging loop.
- Evaluation suite for real-model runs (success rate, cost per completed task).
