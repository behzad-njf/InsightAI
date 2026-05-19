"""Generate a natural-language answer from query results (Phase 6.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.answer import (
    GenerateAnswerRequest,
    GenerateAnswerResult,
    GenerateAnswerStreamChunk,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.domain.ports.answer_generator import IAnswerGenerator
    from insightai.infrastructure.config.settings import Settings


class GenerateAnswerUseCase:
    """
    Turn question + SQL + ``QueryResult`` into a grounded prose answer.

    Delegates to ``IAnswerGenerator`` (LLM + ``prompts/answer_generation/``).
    """

    def __init__(
        self,
        answer_generator: IAnswerGenerator,
        settings: Settings | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._answer_generator = answer_generator
        self._settings = settings or get_settings()

    async def execute(self, request: GenerateAnswerRequest) -> GenerateAnswerResult:
        generation_request = request.to_generation_request()
        answer = await self._answer_generator.generate(generation_request)
        return GenerateAnswerResult.from_parts(request, answer)

    async def execute_stream(
        self,
        request: GenerateAnswerRequest,
    ) -> AsyncIterator[GenerateAnswerStreamChunk]:
        """Stream answer tokens, then a terminal chunk with ``GenerateAnswerResult``."""
        generation_request = request.to_generation_request()
        async for chunk in self._answer_generator.generate_stream(generation_request):
            if chunk.kind == "token" and chunk.text_delta:
                yield GenerateAnswerStreamChunk.token(chunk.text_delta)
            elif chunk.kind == "done" and chunk.result is not None:
                yield GenerateAnswerStreamChunk.done(
                    GenerateAnswerResult.from_parts(request, chunk.result),
                )
