"""LangChain-backed provider. Works with any chat model that supports structured output."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from forgeflow.config import Settings
from forgeflow.llm.base import LLMError, T
from forgeflow.security.untrusted import UNTRUSTED_POLICY
from forgeflow.telemetry import RunHandle

_MAX_ATTEMPTS = 2


class LangChainLLM:
    simulated = False

    def __init__(self, settings: Settings) -> None:
        self.provider: str = settings.llm_provider
        self.model = settings.llm_model
        kwargs: dict[str, Any] = {"max_tokens": settings.llm_max_tokens, "timeout": settings.llm_timeout_seconds}
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key.get_secret_value()
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        try:
            self._chat = init_chat_model(self.model, model_provider=self.provider, **kwargs)
        except ImportError as exc:  # provider package not installed
            raise LLMError(
                f"LLM provider '{self.provider}' needs its LangChain integration package "
                f"(install the 'forgeflow[{self.provider}]' extra)"
            ) from exc

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
        runnable = self._chat.with_structured_output(schema, include_raw=True)
        messages: list[Any] = [SystemMessage(content=f"{system}\n\n{UNTRUSTED_POLICY}"), HumanMessage(content=prompt)]
        last_error = ""
        for _ in range(_MAX_ATTEMPTS):
            result = await runnable.ainvoke(messages, config={"run_name": f"forgeflow.{purpose}"})
            raw = result.get("raw")
            usage = getattr(raw, "usage_metadata", None) or {}
            run.add_usage(
                self.provider, self.model, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            )
            parsed = result.get("parsed")
            err = result.get("parsing_error")
            if parsed is not None and err is None:
                try:
                    # Re-validate: some providers return dicts or skip validators.
                    return schema.model_validate(parsed.model_dump() if hasattr(parsed, "model_dump") else parsed)
                except ValidationError as exc:
                    err = exc
            last_error = str(err)[:2000]
            messages.append(
                HumanMessage(
                    content=f"Your previous output failed validation:\n{last_error}\nReturn a corrected response."
                )
            )
        raise LLMError(f"{purpose}: model output failed validation after {_MAX_ATTEMPTS} attempts: {last_error}")
