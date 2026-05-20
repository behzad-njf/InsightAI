"""LLM-backed RAG answer generator (Phase 10.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from insightai.domain.models.answer import (
    AnswerGenerationResult,
    AnswerGenerationStreamChunk,
)
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.hybrid import RAGRetrievalResult
from insightai.domain.models.llm import LLMRequest, LLMStreamChunk, join_stream_text
from insightai.domain.ports.rag_answer_generator import IRAGAnswerGenerator
from insightai.infrastructure.ai.answer_response_parser import parse_answer_generation_llm_output
from insightai.infrastructure.ai.providers.base import terminal_stream_metadata
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.prompts.rag_loader import (
    RAGAnswerPromptBundle,
    load_rag_answer_prompts,
    load_rag_answer_stream_prompts,
)
from insightai.infrastructure.rag.source_format import format_rag_sources_for_prompt

if TYPE_CHECKING:
    from insightai.domain.models.llm import LLMMessage
    from insightai.domain.ports.ai_framework import IAIFramework

logger = get_logger(__name__)

_DEFAULT_MAX_COMPLETION_TOKENS = 2048
_EMPTY_QUERY_RESULT = QueryResult(
    columns=[QueryColumn(name="_rag")],
    rows=[],
    row_count=0,
    executed_at=datetime.now(UTC),
    truncated=False,
)


class LLMRAGAnswerGenerator(IRAGAnswerGenerator):
    """Answer document questions from retrieved chunks via ``IAIFramework``."""

    def __init__(
        self,
        framework: IAIFramework,
        settings: Settings | None = None,
        *,
        prompt_bundle: RAGAnswerPromptBundle | None = None,
        stream_prompt_bundle: RAGAnswerPromptBundle | None = None,
        max_completion_tokens: int = _DEFAULT_MAX_COMPLETION_TOKENS,
    ) -> None:
        self._framework = framework
        self._settings = settings or get_settings()
        self._prompts = prompt_bundle or load_rag_answer_prompts(self._settings)
        self._stream_prompts = stream_prompt_bundle or load_rag_answer_stream_prompts(
            self._settings,
        )
        self._max_completion_tokens = max_completion_tokens

    def _build_messages(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        bundle: RAGAnswerPromptBundle,
    ) -> list[LLMMessage]:
        from insightai.domain.models.llm import LLMMessage, LLMRole

        excerpts = format_rag_sources_for_prompt(retrieval)
        return [
            LLMMessage(role=LLMRole.SYSTEM, content=bundle.render_system()),
            LLMMessage(
                role=LLMRole.USER,
                content=bundle.render_user(question=question, document_excerpts=excerpts),
            ),
        ]

    async def generate(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AnswerGenerationResult:
        messages = self._build_messages(
            question=question,
            retrieval=retrieval,
            bundle=self._prompts,
        )
        llm_request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=self._max_completion_tokens,
            metadata={"task": "rag_answer_generation"},
        )
        logger.info(
            "rag_answer_generation_start",
            source_count=len(retrieval.sources),
        )
        llm_response = await self._framework.complete(llm_request)
        output = parse_answer_generation_llm_output(llm_response.content)
        result = AnswerGenerationResult.from_llm_output(
            output,
            query_result=_EMPTY_QUERY_RESULT,
            usage=llm_response.usage,
            model=llm_response.model,
            provider=llm_response.provider,
            finish_reason=llm_response.finish_reason,
        )
        logger.info(
            "rag_answer_generation_complete",
            answer_length=len(result.answer),
        )
        return result

    async def generate_stream(
        self,
        *,
        question: str,
        retrieval: RAGRetrievalResult,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[AnswerGenerationStreamChunk]:
        messages = self._build_messages(
            question=question,
            retrieval=retrieval,
            bundle=self._stream_prompts,
        )
        llm_request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=self._max_completion_tokens,
            metadata={"task": "rag_answer_generation_stream"},
        )
        collected: list[LLMStreamChunk] = []
        async for chunk in self._framework.complete_stream(llm_request):
            collected.append(chunk)
            if chunk.text:
                yield AnswerGenerationStreamChunk.token(chunk.text)

        finish_reason, usage = terminal_stream_metadata(collected)
        llm_provider = self._framework.get_llm_provider()
        model_name = model or llm_provider.default_model
        result = AnswerGenerationResult.from_streamed_text(
            join_stream_text(collected),
            query_result=_EMPTY_QUERY_RESULT,
            usage=usage,
            model=model_name,
            provider=llm_provider.provider_kind,
            finish_reason=finish_reason,
        )
        yield AnswerGenerationStreamChunk.done(result)
