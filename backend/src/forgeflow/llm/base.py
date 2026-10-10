"""Provider-independent structured LLM interface used by all agents."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from forgeflow.telemetry import RunHandle

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class StructuredLLM(Protocol):
    provider: str
    model: str
    simulated: bool

    async def structured(
        self,
        schema: type[T],
        *,
        purpose: str,
        system: str,
        prompt: str,
        run: RunHandle,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Return an instance of ``schema``.

        ``purpose`` names the agent step (``plan``, ``codegen``, ``diagnose`` ...).
        ``context`` carries the structured inputs behind the prompt; real providers
        ignore it, the deterministic demo provider uses it instead of the prompt.
        """
        ...
