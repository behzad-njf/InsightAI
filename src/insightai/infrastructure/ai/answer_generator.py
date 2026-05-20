"""LLM-backed answer generator — prompts + framework completion (Phase 6.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from insightai.domain.models.answer import (
    AnswerGenerationRequest,
    AnswerGenerationResult,
    AnswerGenerationStreamChunk,
)
from insightai.domain.models.llm import LLMRequest, LLMStreamChunk, join_stream_text
from insightai.domain.ports.answer_generator import IAnswerGenerator
from insightai.infrastructure.ai.answer_response_parser import parse_answer_generation_llm_output
from insightai.infrastructure.ai.providers.base import terminal_stream_metadata
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.prompts.hybrid_loader import (
    HybridAnswerPromptBundle,
    load_hybrid_answer_prompts,
    load_hybrid_answer_stream_prompts,
    render_hybrid_answer_messages,
)
from insightai.infrastructure.prompts.loader import (
    AnswerGenerationPromptBundle,
    load_answer_generation_prompts,
    load_answer_generation_stream_prompts,
    render_answer_generation_messages,
    render_answer_generation_stream_messages,
)
from insightai.infrastructure.prompts.result_sampling import sample_rows_for_prompt

if TYPE_CHECKING:
    from insightai.domain.ports.ai_framework import IAIFramework

logger = get_logger(__name__)

_DEFAULT_MAX_COMPLETION_TOKENS = 2048


class LLMAnswerGenerator(IAnswerGenerator):
    """
    Summarizes query results via ``IAIFramework`` and answer prompts.

    - ``generate()`` — JSON-shaped answers (``system.md`` / ``user.md``)
    - ``generate_stream()`` — plain prose tokens (``stream_system.md`` / ``stream_user.md``)
    """

    def __init__(
        self,
        framework: IAIFramework,
        settings: Settings | None = None,
        *,
        prompt_bundle: AnswerGenerationPromptBundle | None = None,
        stream_prompt_bundle: AnswerGenerationPromptBundle | None = None,
        hybrid_prompt_bundle: HybridAnswerPromptBundle | None = None,
        hybrid_stream_prompt_bundle: HybridAnswerPromptBundle | None = None,
        max_completion_tokens: int = _DEFAULT_MAX_COMPLETION_TOKENS,
        default_max_display_rows: int | None = None,
    ) -> None:
        self._framework = framework
        self._settings = settings or get_settings()
        self._prompts = prompt_bundle or load_answer_generation_prompts(self._settings)
        self._stream_prompts = stream_prompt_bundle or load_answer_generation_stream_prompts(
            self._settings,
        )
        self._hybrid_prompts = hybrid_prompt_bundle or load_hybrid_answer_prompts(self._settings)
        self._hybrid_stream_prompts = (
            hybrid_stream_prompt_bundle or load_hybrid_answer_stream_prompts(self._settings)
        )
        self._max_completion_tokens = max_completion_tokens
        self._default_max_display_rows = (
            default_max_display_rows
            if default_max_display_rows is not None
            else self._settings.answer_max_prompt_rows
        )

    def _resolve_max_display_rows(self, request: AnswerGenerationRequest) -> int:
        if request.max_display_rows is not None:
            return request.max_display_rows
        return self._default_max_display_rows

    async def generate(self, request: AnswerGenerationRequest) -> AnswerGenerationResult:
        max_display = self._resolve_max_display_rows(request)
        sample = sample_rows_for_prompt(
            request.query_result.rows,
            max_rows=max_display,
        )
        task = "answer_generation"
        if request.document_context:
            task = "answer_generation_hybrid"
            messages = render_hybrid_answer_messages(
                question=request.question,
                sql=request.sql,
                query_result=request.query_result,
                document_excerpts=request.document_context,
                max_display_rows=max_display,
                settings=self._settings,
                bundle=self._hybrid_prompts,
            )
        else:
            messages = render_answer_generation_messages(
                question=request.question,
                sql=request.sql,
                query_result=request.query_result,
                max_display_rows=max_display,
                settings=self._settings,
                bundle=self._prompts,
            )
        llm_request = LLMRequest(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=self._max_completion_tokens,
            metadata={"task": task},
        )

        logger.info(
            "answer_generation_start",
            row_count=request.query_result.row_count,
            truncated=request.query_result.truncated,
            display_rows=max_display,
            rows_sampled=sample.was_sampled,
            sampling_strategy=sample.strategy,
        )
        llm_response = await self._framework.complete(llm_request)
        output = parse_answer_generation_llm_output(llm_response.content)

        result = AnswerGenerationResult.from_llm_output(
            output,
            query_result=request.query_result,
            usage=llm_response.usage,
            model=llm_response.model,
            provider=llm_response.provider,
            finish_reason=llm_response.finish_reason,
        )
        logger.info(
            "answer_generation_complete",
            row_count=result.row_count,
            truncation_noted=result.truncation_noted,
            answer_length=len(result.answer),
        )
        return result

    async def generate_stream(
        self,
        request: AnswerGenerationRequest,
    ) -> AsyncIterator[AnswerGenerationStreamChunk]:
        max_display = self._resolve_max_display_rows(request)
        sample = sample_rows_for_prompt(
            request.query_result.rows,
            max_rows=max_display,
        )
        if request.document_context:
            messages = render_hybrid_answer_messages(
                question=request.question,
                sql=request.sql,
                query_result=request.query_result,
                document_excerpts=request.document_context,
                max_display_rows=max_display,
                settings=self._settings,
                bundle=self._hybrid_stream_prompts,
            )
            stream_task = "answer_generation_hybrid_stream"
        else:
            messages = render_answer_generation_stream_messages(
                question=request.question,
                sql=request.sql,
                query_result=request.query_result,
                max_display_rows=max_display,
                settings=self._settings,
                bundle=self._stream_prompts,
            )
            stream_task = "answer_generation_stream"
        llm_request = LLMRequest(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=self._max_completion_tokens,
            metadata={"task": stream_task},
        )

        logger.info(
            "answer_generation_stream_start",
            row_count=request.query_result.row_count,
            truncated=request.query_result.truncated,
            display_rows=max_display,
            rows_sampled=sample.was_sampled,
            sampling_strategy=sample.strategy,
        )

        collected: list[LLMStreamChunk] = []
        async for chunk in self._framework.complete_stream(llm_request):
            collected.append(chunk)
            if chunk.text:
                yield AnswerGenerationStreamChunk.token(chunk.text)

        finish_reason, usage = terminal_stream_metadata(collected)
        provider = self._framework.get_llm_provider()
        model = request.model or provider.default_model
        result = AnswerGenerationResult.from_streamed_text(
            join_stream_text(collected),
            query_result=request.query_result,
            usage=usage,
            model=model,
            provider=provider.provider_kind,
            finish_reason=finish_reason,
        )
        logger.info(
            "answer_generation_stream_complete",
            row_count=result.row_count,
            truncation_noted=result.truncation_noted,
            answer_length=len(result.answer),
        )
        yield AnswerGenerationStreamChunk.done(result)
