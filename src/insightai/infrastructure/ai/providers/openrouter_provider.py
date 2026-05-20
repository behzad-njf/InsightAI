"""OpenRouter LLM provider — official ``openrouter`` SDK."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

from openrouter import OpenRouter
from openrouter.errors import (
    BadGatewayResponseError,
    EdgeNetworkTimeoutResponseError,
    NoResponseError,
    OpenRouterDefaultError,
    ProviderOverloadedResponseError,
    RequestTimeoutResponseError,
    ServiceUnavailableResponseError,
    TooManyRequestsResponseError,
)
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

_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
    NoResponseError,
    EdgeNetworkTimeoutResponseError,
    RequestTimeoutResponseError,
    ServiceUnavailableResponseError,
    BadGatewayResponseError,
    ProviderOverloadedResponseError,
    TooManyRequestsResponseError,
)


class OpenRouterLLMProvider(ILLMProvider):
    """Chat completions via the official OpenRouter Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenRouter(api_key=settings.require_openrouter_api_key())

    @property
    def provider_kind(self) -> LLMProviderKind:
        return LLMProviderKind.OPENROUTER

    @property
    def default_model(self) -> str:
        return self._settings.openrouter_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await asyncio.to_thread(self._complete_with_retry, request)
        except _RETRYABLE as exc:
            raise LLMProviderUnavailableError(provider_error_message(exc)) from exc
        except OpenRouterDefaultError as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        try:
            async for chunk in self._stream_chunks_async(request):
                yield chunk
        except _RETRYABLE as exc:
            raise LLMProviderUnavailableError(provider_error_message(exc)) from exc
        except OpenRouterDefaultError as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(provider_error_message(exc)) from exc

    def _complete_with_retry(self, request: LLMRequest) -> LLMResponse:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._settings.openrouter_max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        def _call() -> LLMResponse:
            return self._complete_sync(request)

        return _call()

    def _stream_chunks_with_retry(self, request: LLMRequest) -> list[LLMStreamChunk]:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._settings.openrouter_max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        def _call() -> list[LLMStreamChunk]:
            return list(self._iter_stream_chunks_sync(request))

        return _call()

    async def _stream_chunks_async(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[LLMStreamChunk]:
        import queue
        import threading

        sync_queue: queue.Queue[LLMStreamChunk | BaseException | None] = queue.Queue()

        def worker() -> None:
            try:
                for chunk in self._stream_chunks_with_retry(request):
                    sync_queue.put(chunk)
            except BaseException as exc:
                sync_queue.put(exc)
            finally:
                sync_queue.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while True:
            item = await asyncio.to_thread(sync_queue.get)
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
        await asyncio.to_thread(thread.join)

    def _complete_sync(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.default_model
        kwargs = self._chat_kwargs(request, model=model, stream=request.stream)

        if request.stream:
            try:
                return self._complete_streaming(**kwargs)
            except Exception as stream_exc:
                logger.warning(
                    "openrouter_stream_failed_retrying_non_stream",
                    error=provider_error_message(stream_exc),
                )
                kwargs["stream"] = False
                return self._complete_non_streaming(**kwargs)

        return self._complete_non_streaming(**kwargs)

    def _chat_kwargs(self, request: LLMRequest, *, model: str, stream: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": to_chat_payload(request.messages),
            "temperature": request.temperature,
            "stream": stream,
            "timeout_ms": self._settings.openrouter_timeout_seconds * 1000,
        }
        if request.max_tokens is not None:
            kwargs["max_completion_tokens"] = request.max_tokens
        referer = self._settings.openrouter_http_referer
        if referer and referer.strip():
            kwargs["http_referer"] = referer.strip()
        title = self._settings.openrouter_app_title
        if title and title.strip():
            kwargs["x_open_router_title"] = title.strip()
        return kwargs

    def _complete_non_streaming(self, **kwargs: Any) -> LLMResponse:
        send_kwargs = {**kwargs, "stream": False}
        completion = self._client.chat.send(**send_kwargs)
        choice = completion.choices[0]
        content = choice.message.content if choice.message else ""
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        return LLMResponse(
            content=content or "",
            model=kwargs["model"],
            provider=LLMProviderKind.OPENROUTER,
            usage=token_usage_from_payload(completion.usage),
            finish_reason=choice.finish_reason,
        )

    def _complete_streaming(self, **kwargs: Any) -> LLMResponse:
        collected = list(self._iter_stream_chunks_sync_from_kwargs(**kwargs))
        finish_reason, usage = terminal_stream_metadata(collected)
        return LLMResponse(
            content=join_stream_text(collected),
            model=kwargs["model"],
            provider=LLMProviderKind.OPENROUTER,
            usage=usage,
            finish_reason=finish_reason,
        )

    def _iter_stream_chunks_sync(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        model = request.model or self.default_model
        return self._iter_stream_chunks_sync_from_kwargs(
            **self._chat_kwargs(request, model=model, stream=True),
        )

    def _iter_stream_chunks_sync_from_kwargs(self, **kwargs: Any) -> Iterator[LLMStreamChunk]:
        send_kwargs = {**kwargs, "stream": True}
        stream = self._client.chat.send(**send_kwargs)
        yield from iter_sdk_stream_chunks(stream)
