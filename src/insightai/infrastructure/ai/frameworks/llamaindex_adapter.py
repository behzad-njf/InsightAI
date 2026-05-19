"""LlamaIndex framework adapter — configures global LLM and delegates completions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.llm import AIFrameworkKind, LLMProviderKind
from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.llm_provider import ILLMProvider  # noqa: TC001
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.domain.models.llm import LLMRequest, LLMResponse

logger = get_logger(__name__)

# Groq exposes an OpenAI-compatible API for LlamaIndex tooling (RAG in Phase 10).
GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"


class LlamaIndexFrameworkAdapter(IAIFramework):
    """
    Primary AI framework adapter.

    Phase 1: registers a LlamaIndex-compatible LLM for future RAG workflows and
    delegates ``complete()`` to the configured ``ILLMProvider``.
    """

    def __init__(self, provider: ILLMProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings
        self._configure_llamaindex_llm()

    @property
    def framework_kind(self) -> AIFrameworkKind:
        return AIFrameworkKind.LLAMAINDEX

    def get_llm_provider(self) -> ILLMProvider:
        return self._provider

    async def complete(self, request: LLMRequest) -> LLMResponse:
        logger.debug(
            "llamaindex_complete_delegate",
            provider=self._provider.provider_kind.value,
        )
        return await self._provider.complete(request)

    def _configure_llamaindex_llm(self) -> None:
        """Set LlamaIndex Settings.llm so future RAG/index code can use the same credentials."""
        try:
            from llama_index.core import Settings as LlamaSettings
            from llama_index.llms.openai import OpenAI
        except ImportError as exc:
            logger.warning("llamaindex_import_failed", error=str(exc))
            return

        if self._provider.provider_kind == LLMProviderKind.GROQ:
            llm = OpenAI(
                model=self._settings.groq_model,
                api_key=self._settings.require_groq_api_key(),
                api_base=GROQ_OPENAI_BASE_URL,
                temperature=self._settings.llm_temperature,
                timeout=float(self._settings.groq_timeout_seconds),
            )
        elif self._provider.provider_kind == LLMProviderKind.OPENAI:
            llm = OpenAI(
                model=self._settings.openai_model,
                api_key=self._settings.require_openai_api_key(),
                temperature=self._settings.llm_temperature,
                timeout=float(self._settings.openai_timeout_seconds),
            )
        else:
            logger.warning(
                "llamaindex_llm_not_configured",
                provider=self._provider.provider_kind.value,
            )
            return

        LlamaSettings.llm = llm
        logger.info(
            "llamaindex_llm_configured",
            provider=self._provider.provider_kind.value,
            model=llm.model,
        )
