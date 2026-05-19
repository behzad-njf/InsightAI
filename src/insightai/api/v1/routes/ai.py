"""AI routes — LLM smoke endpoints (SQL generation in later phases)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from insightai.api.deps import get_llm_completion_use_case, get_settings
from insightai.api.schemas.llm import (
    LLMCompleteRequest,
    LLMCompleteResponse,
    LLMStreamErrorSchema,
    LLMStreamTokenSchema,
    TokenUsageSchema,
)
from insightai.api.sse import format_sse
from insightai.application.use_cases.llm_completion import LLMCompletionUseCase
from insightai.domain.exceptions import LLMProviderError, LLMProviderUnavailableError
from insightai.domain.models.llm import LLMResponse, join_stream_text
from insightai.infrastructure.ai.providers.base import terminal_stream_metadata
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/complete", response_model=LLMCompleteResponse)
async def complete(
    body: LLMCompleteRequest,
    use_case: LLMCompletionUseCase = Depends(get_llm_completion_use_case),
    settings: Settings = Depends(get_settings),
) -> LLMCompleteResponse:
    """
    Run a chat completion through the configured LLM provider/framework.

    Smoke-test endpoint for Phase 1 — not yet wired to SQL or schema context.
    """
    domain_request = body.to_domain(default_temperature=settings.llm_temperature)
    response = await use_case.execute(domain_request)
    return _to_complete_response(response, settings=settings)


@router.post("/complete/stream")
async def complete_stream(
    body: LLMCompleteRequest,
    use_case: LLMCompletionUseCase = Depends(get_llm_completion_use_case),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Stream a raw LLM completion via SSE (``token`` events, then ``done``).

    Public smoke test — same request body as ``POST /ai/complete``. Not used by the
    product chat pipeline (use ``POST /api/v1/chat/stream`` for that).
    """
    domain_request = body.to_domain(default_temperature=settings.llm_temperature)

    async def event_generator() -> AsyncIterator[str]:
        collected = []
        try:
            async for chunk in use_case.execute_stream(domain_request):
                collected.append(chunk)
                if chunk.text:
                    yield format_sse(
                        "token",
                        LLMStreamTokenSchema(text=chunk.text).model_dump(),
                    )
            finish_reason, usage = terminal_stream_metadata(collected)
            provider = use_case.get_llm_provider()
            model = domain_request.model or provider.default_model
            response = _to_complete_response(
                LLMResponse(
                    content=join_stream_text(collected),
                    model=model,
                    provider=provider.provider_kind,
                    usage=usage,
                    finish_reason=finish_reason,
                ),
                settings=settings,
            )
            yield format_sse("done", response.model_dump())
        except (LLMProviderError, LLMProviderUnavailableError) as exc:
            logger.warning("ai_complete_stream_failed", error=str(exc))
            yield format_sse(
                "error",
                LLMStreamErrorSchema(
                    error_message=str(exc),
                    error_code=exc.__class__.__name__,
                ).model_dump(),
            )
        except Exception as exc:
            logger.exception("ai_complete_stream_failed", error=str(exc))
            yield format_sse(
                "error",
                LLMStreamErrorSchema(
                    error_message=str(exc),
                    error_code="pipeline_error",
                ).model_dump(),
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


def _to_complete_response(response: LLMResponse, *, settings: Settings) -> LLMCompleteResponse:
    return LLMCompleteResponse(
        content=response.content,
        model=response.model,
        provider=response.provider.value,
        usage=TokenUsageSchema(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        ),
        finish_reason=response.finish_reason,
        raw=response.raw if settings.debug else None,
    )
