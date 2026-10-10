"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from forgeflow.schemas import Workflow

T = TypeVar("T")

# SQLite returns naive datetimes; everything is stored in UTC, so make that explicit on the wire.
UTCDateTime = Annotated[datetime, AfterValidator(lambda d: d if d.tzinfo else d.replace(tzinfo=UTC))]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Me(BaseModel):
    id: str
    name: str
    role: str


class ExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_id: str
    workflow: Workflow = Workflow.feature
    request: str = Field(default="", max_length=8000)
    params: dict[str, Any] = Field(default_factory=dict)


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workflow: str
    repository_id: str
    repository_name: str | None = None
    request: str
    params: dict[str, Any]
    status: str
    current_node: str | None
    summary: str | None
    error: str | None
    created_by: str
    source: str
    created_at: UTCDateTime
    started_at: UTCDateTime | None
    finished_at: UTCDateTime | None
    duration_ms: int | None = None


class ExecutionDetail(ExecutionOut):
    report: dict[str, Any] | None
    state: dict[str, Any] | None = None
    pending_approval_id: str | None = None
    simulated: bool = False


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    type: str
    agent_id: str | None
    node: str | None
    message: str
    data: dict[str, Any]
    created_at: UTCDateTime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    execution_id: str
    agent_id: str
    node: str
    attempt: int
    status: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    llm_calls: int
    error: str | None
    trace_id: str | None
    started_at: UTCDateTime
    ended_at: UTCDateTime | None
    duration_ms: int | None


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    execution_id: str
    agent_run_id: str | None
    agent_id: str
    tool: str
    arguments: dict[str, Any]
    status: str
    result_summary: str | None
    error: str | None
    started_at: UTCDateTime
    duration_ms: int | None


class TraceOut(BaseModel):
    execution_id: str
    runs: list[AgentRunOut]
    tool_calls: list[ToolCallOut]
    totals: dict[str, Any]


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    responsibilities: list[str]
    tools: list[str]
    uses_llm: bool
    state: Literal["active", "idle", "error"]
    active_executions: list[str]
    recent_nodes: list[str]
    last_run: AgentRunOut | None
    runs_total: int
    failures_total: int
    avg_duration_ms: int | None
    recent_tools: list[ToolCallOut]


class RepositoryConnect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["github", "local"]
    full_name: str | None = Field(default=None, description="owner/name or GitHub URL (github)")
    path: str | None = Field(default=None, description="Directory under an allowed local root (local)")


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    full_name: str
    default_branch: str
    description: str | None
    analyzed_at: UTCDateTime | None
    created_at: UTCDateTime
    summary: dict[str, Any] | None = None


class RepositoryDetail(RepositoryOut):
    analysis: dict[str, Any] | None
    memory: dict[str, Any]
    history: list[dict[str, Any]]


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    execution_id: str
    action: str
    title: str
    details: dict[str, Any]
    requested_permissions: list[Any]
    status: str
    decided_by: str | None
    decision_comment: str | None
    created_at: UTCDateTime
    decided_at: UTCDateTime | None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, max_length=2000)


class WorkflowOut(BaseModel):
    id: str
    title: str
    description: str
    graph: dict[str, Any]
