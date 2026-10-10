"""Agent registry and the shared service container handed to every agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from forgeflow.config import Settings
from forgeflow.db.session import Database
from forgeflow.events.bus import EventBus
from forgeflow.integrations.github import GitHubClient
from forgeflow.llm.base import StructuredLLM
from forgeflow.memory.store import MemoryStore
from forgeflow.telemetry import Recorder
from forgeflow.workspace.manager import WorkspaceManager
from forgeflow.workspace.sandbox import Sandbox


@dataclass
class Services:
    settings: Settings
    db: Database
    events: EventBus
    recorder: Recorder
    llm: StructuredLLM
    workspaces: WorkspaceManager
    sandbox: Sandbox
    github: GitHubClient
    memory: MemoryStore


@dataclass(frozen=True)
class AgentInfo:
    id: str
    name: str
    description: str
    responsibilities: list[str]
    tools: list[str] = field(default_factory=list)
    uses_llm: bool = True


AGENTS: dict[str, AgentInfo] = {
    a.id: a
    for a in [
        AgentInfo(
            "orchestrator",
            "Engineering Orchestrator",
            "Selects the workflow, resolves task dependencies, dispatches work, enforces limits and escalates.",
            [
                "Workflow selection",
                "Dependency resolution",
                "Parallel dispatch",
                "Retry and timeout limits",
                "Cancellation",
                "Escalation to humans",
                "Final report",
            ],
            ["graph.dispatch", "deps.resolve"],
            uses_llm=False,
        ),
        AgentInfo(
            "repository_analyst",
            "Repository Analyst",
            "Indexes the repository and retrieves focused code context.",
            [
                "Language and framework detection",
                "Module and import analysis",
                "Test and docs discovery",
                "Lexical code retrieval",
                "Repository memory",
            ],
            ["repo.index", "repo.search", "memory.save"],
        ),
        AgentInfo(
            "task_planner",
            "Task Planning Agent",
            "Turns a request into a validated plan of dependent tasks with acceptance criteria.",
            ["Plan generation", "Subtask definition", "Dependencies", "Acceptance criteria", "Risk identification"],
            ["memory.recall"],
        ),
        AgentInfo(
            "code_generator",
            "Code Generation Agent",
            "Produces focused, validated file edits for a task and applies them in the workspace.",
            ["Target file analysis", "Focused patches", "Test updates", "Scope control"],
            ["workspace.read", "workspace.apply_patch"],
        ),
        AgentInfo(
            "debugger",
            "Debugging Agent",
            "Diagnoses failing tests and proposes bounded fixes.",
            ["Failure analysis", "Root cause identification", "Corrective patches", "Attempt tracking"],
            ["workspace.read", "workspace.apply_patch", "memory.recall"],
        ),
        AgentInfo(
            "code_reviewer",
            "Code Review Agent",
            "Reviews the diff with static rules and a model pass; critical findings block progression.",
            ["Static safety checks", "Correctness review", "Security review", "Scope and test coverage"],
            ["diff.static_checks"],
        ),
        AgentInfo(
            "verifier",
            "Verification Agent",
            "Runs allowlisted tests and linters in the sandbox and checks acceptance criteria.",
            ["Test execution", "Lint and compile checks", "Acceptance criteria", "Completion decision"],
            ["sandbox.run"],
        ),
        AgentInfo(
            "pull_request",
            "Pull Request Agent",
            "Prepares the pull request from verified results and publishes it after approval.",
            ["PR description", "Test outcomes", "Known limitations", "Approval request", "PR creation"],
            ["github.push_branch", "github.create_pull"],
        ),
    ]
}
