"""LangChain framework adapter (Phase 10.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.llm import AIFrameworkKind
from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.llm_provider import ILLMProvider  # noqa: TC001
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.domain.models.llm import LLMRequest, LLMResponse

logger = get_logger(__name__)


class LangChainFrameworkAdapter(IAIFramework):
    """
    LangChain framework adapter.

    - ``complete`` / ``complete_stream`` delegate to ``ILLMProvider`` (SQL/RAG LLM paths).
    - Tool-calling agents are run via ``LangChainAgentRunner`` when the optional path is enabled.
    """

    def __init__(self, provider: ILLMProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings
        logger.info(
            "langchain_framework_configured",
            provider=self._provider.provider_kind.value,
        )

    @property
    def framework_kind(self) -> AIFrameworkKind:
        return AIFrameworkKind.LANGCHAIN

    def get_llm_provider(self) -> ILLMProvider:
        return self._provider

    async def complete(self, request: LLMRequest) -> LLMResponse:
        logger.debug(
            "langchain_complete_delegate",
            provider=self._provider.provider_kind.value,
        )
        return await self._provider.complete(request)
