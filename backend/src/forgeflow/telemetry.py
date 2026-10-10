"""Agent-run and tool-call recording plus OpenTelemetry spans.

Each agent invocation becomes an ``agent_runs`` row and an OTel span; each tool call a
``tool_calls`` row and a child span. Token usage and estimated cost are accumulated on
the run as LLM calls complete. Arguments and results are redacted before storage.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

from forgeflow.config import Settings
from forgeflow.db.models import AgentRun, ToolCall, utcnow
from forgeflow.db.session import Database
from forgeflow.events.bus import EventBus
from forgeflow.security.redaction import redact, redact_obj

tracer = trace.get_tracer("forgeflow")

# USD per million tokens (input, output). Unknown models are recorded with cost 0.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "demo": (0.0, 0.0),
}


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float:
    if not model:
        return 0.0
    price = MODEL_PRICES.get(model.split(":")[-1])
    if not price:
        return 0.0
    return round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 6)


_configured = False


def configure_tracing(settings: Settings) -> None:
    global _configured
    if _configured:
        return
    _configured = True
    provider = TracerProvider(resource=Resource.create({"service.name": "forgeflow"}))
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces")
            )
        )
    if settings.otel_console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


@dataclass
class RunHandle:
    """Mutable handle for an in-flight agent run."""

    id: str
    execution_id: str
    agent_id: str
    node: str
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def add_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.provider, self.model = provider, model
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.llm_calls += 1


class Recorder:
    def __init__(self, db: Database, events: EventBus) -> None:
        self.db = db
        self.events = events

    @asynccontextmanager
    async def agent_run(
        self, execution_id: str, agent_id: str, node: str, *, attempt: int = 1, message: str = ""
    ) -> AsyncIterator[RunHandle]:
        start = time.perf_counter()
        with tracer.start_as_current_span(f"agent.{agent_id}") as span:
            span.set_attributes(
                {"forgeflow.execution_id": execution_id, "forgeflow.agent": agent_id, "forgeflow.node": node}
            )
            trace_id = format(span.get_span_context().trace_id, "032x")
            async with self.db.session() as s:
                row = AgentRun(
                    execution_id=execution_id, agent_id=agent_id, node=node, attempt=attempt, trace_id=trace_id
                )
                s.add(row)
                await s.flush()
                handle = RunHandle(id=row.id, execution_id=execution_id, agent_id=agent_id, node=node)
            await self.events.emit(
                execution_id,
                "agent.started",
                message or f"{agent_id} started",
                agent_id=agent_id,
                node=node,
                data={"run_id": handle.id, "attempt": attempt},
            )
            status, error = "succeeded", None
            try:
                yield handle
            except BaseException as exc:  # includes cancellation
                import asyncio

                status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
                error = redact(f"{type(exc).__name__}: {exc}")[:2000]
                span.set_status(Status(StatusCode.ERROR, error))
                raise
            finally:
                duration = int((time.perf_counter() - start) * 1000)
                cost = estimate_cost(handle.model, handle.input_tokens, handle.output_tokens)
                span.set_attributes(
                    {
                        "forgeflow.input_tokens": handle.input_tokens,
                        "forgeflow.output_tokens": handle.output_tokens,
                        "forgeflow.cost_usd": cost,
                    }
                )
                async with self.db.session() as s:
                    row2 = await s.get(AgentRun, handle.id)
                    if row2 is not None:
                        row2.status = status
                        row2.error = error
                        row2.provider = handle.provider
                        row2.model = handle.model
                        row2.input_tokens = handle.input_tokens
                        row2.output_tokens = handle.output_tokens
                        row2.llm_calls = handle.llm_calls
                        row2.cost_usd = cost
                        row2.ended_at = utcnow()
                        row2.duration_ms = duration
                if status != "cancelled":
                    await self.events.emit(
                        execution_id,
                        "agent.completed" if status == "succeeded" else "agent.failed",
                        f"{agent_id} {status}" + (f": {error}" if error else ""),
                        agent_id=agent_id,
                        node=node,
                        data={
                            "run_id": handle.id,
                            "duration_ms": duration,
                            "input_tokens": handle.input_tokens,
                            "output_tokens": handle.output_tokens,
                            "cost_usd": cost,
                            **handle.extra,
                        },
                    )

    @asynccontextmanager
    async def tool_call(self, run: RunHandle, tool: str, arguments: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Record a tool call. The yielded dict may receive a ``summary`` key."""
        start = time.perf_counter()
        safe_args = redact_obj(arguments)
        result: dict[str, Any] = {}
        with tracer.start_as_current_span(f"tool.{tool}") as span:
            span.set_attribute("forgeflow.tool", tool)
            async with self.db.session() as s:
                row = ToolCall(
                    execution_id=run.execution_id,
                    agent_run_id=run.id,
                    agent_id=run.agent_id,
                    tool=tool,
                    arguments=safe_args,
                )
                s.add(row)
                await s.flush()
                call_id = row.id
            await self.events.emit(
                run.execution_id,
                "tool.started",
                f"{tool}",
                agent_id=run.agent_id,
                node=run.node,
                data={"tool": tool, "call_id": call_id, "arguments": safe_args},
            )
            status, error = "succeeded", None
            try:
                yield result
            except BaseException as exc:
                status, error = "failed", redact(f"{type(exc).__name__}: {exc}")[:2000]
                span.set_status(Status(StatusCode.ERROR, error))
                raise
            finally:
                duration = int((time.perf_counter() - start) * 1000)
                summary = redact(str(result.get("summary", "")))[:2000] or None
                async with self.db.session() as s:
                    r = await s.get(ToolCall, call_id)
                    if r is not None:
                        r.status, r.error, r.duration_ms, r.result_summary = status, error, duration, summary
                await self.events.emit(
                    run.execution_id,
                    "tool.completed" if status == "succeeded" else "tool.failed",
                    f"{tool} {status}" + (f": {summary}" if summary else ""),
                    agent_id=run.agent_id,
                    node=run.node,
                    data={"tool": tool, "call_id": call_id, "duration_ms": duration, "error": error},
                )
