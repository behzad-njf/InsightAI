"""Generate answers from retrieved document context (Phase 10.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerResult,
    GenerateAnswerStreamChunk,
)
from insightai.infrastructure.rag.citations import enrich_generate_answer_result

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.domain.models.hybrid import RAGRetrievalResult
    from insightai.domain.ports.rag_answer_generator import IRAGAnswerGenerator


class GenerateRAGAnswerUseCase:
    """Turn retrieved chunks into a user-facing document answer."""

    def __init__(self, rag_answer_generator: IRAGAnswerGenerator) -> None:
        self._generator = rag_answer_generator

    async def execute(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> GenerateAnswerResult:
        answer = await self._generator.generate(
            question=question,
            retrieval=retrieval,
            model=model,
            temperature=temperature,
        )
        result = _to_generate_answer_result(question, answer)
        return enrich_generate_answer_result(result, retrieval.sources)

    async def execute_stream(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[GenerateAnswerStreamChunk]:
        async for chunk in self._generator.generate_stream(
            question=question,
            retrieval=retrieval,
            model=model,
            temperature=temperature,
        ):
            if chunk.kind == "done" and chunk.result is not None:
                base = _to_generate_answer_result(question, chunk.result)
                yield GenerateAnswerStreamChunk.done(
                    enrich_generate_answer_result(base, retrieval.sources),
                )
            elif chunk.kind == "token" and chunk.text_delta:
                yield GenerateAnswerStreamChunk.token(chunk.text_delta)


def _to_generate_answer_result(
    question: str,
    answer: AnswerGenerationResult,
) -> GenerateAnswerResult:
    from datetime import UTC, datetime

    from insightai.domain.models.database import QueryColumn, QueryResult

    empty_result = QueryResult(
        columns=[QueryColumn(name="_rag")],
        rows=[],
        row_count=0,
        executed_at=datetime.now(UTC),
        truncated=False,
    )
    return GenerateAnswerResult(
        question=question.strip(),
        sql="",
        query_result=empty_result,
        answer=answer,
    )
