"""LangChain framework stub — implemented in a future phase."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from insightai.domain.exceptions import AIFrameworkNotSupportedError
from insightai.domain.models.llm import AIFrameworkKind
from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.llm_provider import ILLMProvider  # noqa: TC001

if TYPE_CHECKING:
    from insightai.domain.models.llm import LLMRequest, LLMResponse, LLMStreamChunk


class LangChainFrameworkStub(IAIFramework):
    """Placeholder until LangChain agents/tools are integrated (Phase 10)."""

    def __init__(self, provider: ILLMProvider) -> None:
        self._provider = provider

    @property
    def framework_kind(self) -> AIFrameworkKind:
        return AIFrameworkKind.LANGCHAIN

    def get_llm_provider(self) -> ILLMProvider:
        return self._provider

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise AIFrameworkNotSupportedError(self._not_implemented_message())

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        raise AIFrameworkNotSupportedError(self._not_implemented_message())
        yield  # pragma: no cover — makes this an async generator for type checkers

    @staticmethod
    def _not_implemented_message() -> str:
        return "LangChain framework is not implemented yet. Set INSIGHTAI_AI_FRAMEWORK=llamaindex."
