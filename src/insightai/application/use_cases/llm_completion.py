"""LLM completion use case."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.domain.models.llm import LLMRequest, LLMResponse, LLMStreamChunk
    from insightai.domain.ports.ai_framework import IAIFramework
    from insightai.domain.ports.llm_provider import ILLMProvider


class LLMCompletionUseCase:
    """Orchestrates chat completion through the configured AI framework."""

    def __init__(self, framework: IAIFramework) -> None:
        self._framework = framework

    async def execute(self, request: LLMRequest) -> LLMResponse:
        return await self._framework.complete(request)

    async def execute_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """Stream raw provider chunks (smoke test / debugging)."""
        async for chunk in self._framework.complete_stream(request):
            yield chunk

    def get_llm_provider(self) -> ILLMProvider:
        return self._framework.get_llm_provider()
