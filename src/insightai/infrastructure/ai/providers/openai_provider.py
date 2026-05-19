"""OpenAI LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from insightai.domain.exceptions import LLMProviderError, LLMProviderUnavailableError
from insightai.domain.models.llm import (
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    join_stream_text,
)
from insightai.domain.ports.llm_provider import ILLMProvider  # noqa: TC001
from insightai.infrastructure.ai.messages import to_chat_payload
from insightai.infrastructure.ai.providers.base import (
    iter_sdk_stream_chunks,
    provider_error_message,
    terminal_stream_metadata,
    token_usage_from_payload,
)
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

logger = get_logger(__name__)

_RETRYABLE = (APIConnectionError, RateLimitError, TimeoutError)


class OpenAILLMProvider(ILLMProvider):
    """OpenAI chat completions via ``openai.AsyncOpenAI``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.require_openai_api_key(),
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

    @property
    def provider_kind(self) -> LLMProviderKind:
        return LLMProviderKind.OPENAI

    @property
    def default_model(self) -> str:
        return self._settings.openai_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await self._complete_with_retry(request)
        except _RETRYABLE as exc:
            raise LLMProviderUnavailableError(provider_error_message(exc)) from exc
        except APIStatusError as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        try:
            async for chunk in self._iter_stream_chunks(request):
                yield chunk
        except _RETRYABLE as exc:
            raise LLMProviderUnavailableError(provider_error_message(exc)) from exc
        except APIStatusError as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc

    async def _complete_with_retry(self, request: LLMRequest) -> LLMResponse:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._settings.openai_max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        async def _call() -> LLMResponse:
            return await self._complete_once(request)

        return await _call()

    async def _complete_once(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.default_model
        messages = to_chat_payload(request.messages)

        if request.stream:
            try:
                return await self._complete_streaming(model, messages, request)
            except Exception as stream_exc:
                logger.warning(
                    "openai_stream_failed_retrying_non_stream",
                    error=provider_error_message(stream_exc),
                )

        completion = await self._client.chat.completions.create(
            model=model,
            messages=cast("Any", messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
        )
        choice = completion.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=model,
            provider=LLMProviderKind.OPENAI,
            usage=token_usage_from_payload(completion.usage),
            finish_reason=choice.finish_reason,
        )

    async def _complete_streaming(
        self,
        model: str,
        messages: list[dict[str, str]],
        request: LLMRequest,
    ) -> LLMResponse:
        collected: list[LLMStreamChunk] = []
        async for chunk in self._iter_stream_chunks(request, model=model, messages=messages):
            collected.append(chunk)
        finish_reason, usage = terminal_stream_metadata(collected)
        return LLMResponse(
            content=join_stream_text(collected),
            model=model,
            provider=LLMProviderKind.OPENAI,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def _iter_stream_chunks(
        self,
        request: LLMRequest,
        *,
        model: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        resolved_model = model or request.model or self.default_model
        resolved_messages = messages if messages is not None else to_chat_payload(request.messages)
        stream = await self._client.chat.completions.create(
            model=resolved_model,
            messages=cast("Any", resolved_messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            for domain_chunk in iter_sdk_stream_chunks([chunk]):
                yield domain_chunk
