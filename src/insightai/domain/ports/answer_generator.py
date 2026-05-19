"""Answer generator port — question + SQL + query result → natural language."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.answer import (
        AnswerGenerationRequest,
        AnswerGenerationResult,
        AnswerGenerationStreamChunk,
    )


class IAnswerGenerator(ABC):
    """
    Summarizes read-only query results for the user.

    Implementations load prompts from ``prompts/answer_generation/``, call the LLM,
    and parse structured JSON (Phase 6.2) or stream plain prose (streaming path).
    """

    @abstractmethod
    async def generate(
        self,
        request: AnswerGenerationRequest,
    ) -> AnswerGenerationResult:
        """
        Produce a grounded natural-language answer.

        Raises:
            LLMProviderError: Provider returned an error response.
            LLMProviderUnavailableError: Network or rate-limit failure.
            AnswerGenerationError: Unparseable or invalid model output.
            PromptNotFoundError: Required prompt templates are missing.
        """

    async def generate_stream(
        self,
        request: AnswerGenerationRequest,
    ) -> AsyncIterator[AnswerGenerationStreamChunk]:
        """
        Stream answer text deltas, then a terminal chunk with the full result.

        Default: single token event + done via ``generate()`` (non-streaming LLM).
        """
        result = await self.generate(request)
        if result.answer:
            from insightai.domain.models.answer import AnswerGenerationStreamChunk

            yield AnswerGenerationStreamChunk.token(result.answer)
        from insightai.domain.models.answer import AnswerGenerationStreamChunk

        yield AnswerGenerationStreamChunk.done(result)
