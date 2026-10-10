from __future__ import annotations

from forgeflow.config import Settings
from forgeflow.llm.base import LLMError, StructuredLLM


def build_llm(settings: Settings) -> StructuredLLM:
    if settings.llm_provider == "demo":
        from forgeflow.llm.demo import DemoLLM

        return DemoLLM()
    from forgeflow.llm.langchain_provider import LangChainLLM

    return LangChainLLM(settings)


__all__ = ["LLMError", "StructuredLLM", "build_llm"]
