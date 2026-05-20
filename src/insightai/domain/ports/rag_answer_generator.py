"""RAG-only answer generation port (Phase 10.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.domain.models.answer import AnswerGenerationResult, AnswerGenerationStreamChunk
    from insightai.domain.models.hybrid import RAGRetrievalResult


class IRAGAnswerGenerator(ABC):
    """Summarize retrieved document chunks for the user (no SQL execution)."""

    @abstractmethod
    async def generate(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AnswerGenerationResult:
        """Produce a grounded answer citing retrieved sources when possible."""

    async def generate_stream(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[AnswerGenerationStreamChunk]:
        """Stream plain-prose answer tokens, then a terminal result chunk."""
        result = await self.generate(
            question=question,
            retrieval=retrieval,
            model=model,
            temperature=temperature,
        )
        from insightai.domain.models.answer import AnswerGenerationStreamChunk

        if result.answer:
            yield AnswerGenerationStreamChunk.token(result.answer)
        yield AnswerGenerationStreamChunk.done(result)
