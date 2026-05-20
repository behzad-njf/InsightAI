"""ILLMProvider decorator that logs per-call token usage (Phase 8.2)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from insightai.domain.models.llm import (
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)
from insightai.domain.ports.llm_provider import ILLMProvider
from insightai.infrastructure.observability.llm_usage import (
    build_llm_usage_from_response,
    build_llm_usage_record,
    terminal_stream_usage,
)
from insightai.infrastructure.observability.metrics import record_llm_request
from insightai.infrastructure.observability.structlog_audit import NullAuditLogger
from insightai.infrastructure.observability.tracing import set_span_attributes, start_span

if TYPE_CHECKING:
    from insightai.domain.ports.audit_logger import IAuditLogger
    from insightai.infrastructure.config.settings import Settings


class ObservingLLMProvider(ILLMProvider):
    """
    Wrap an LLM provider and emit ``llm_usage`` audit events after each call.

    All product LLM traffic (SQL, answer, smoke ``/ai/complete``) goes through this
    wrapper when ``INSIGHTAI_OBSERVABILITY_LLM_USAGE_ENABLED=true``.
    """

    def __init__(
        self,
        inner: ILLMProvider,
        settings: Settings,
        audit: IAuditLogger | None = None,
    ) -> None:
        self._inner = inner
        self._settings = settings
        self._audit = audit or NullAuditLogger()

    @property
    def provider_kind(self) -> LLMProviderKind:
        return self._inner.provider_kind

    @property
    def default_model(self) -> str:
        return self._inner.default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        task = request.metadata.get("task")
        task_attr = task if isinstance(task, str) else None
        started = time.perf_counter()
        try:
            with start_span(
                "insightai.llm",
                attributes={
                    "llm.provider": self.provider_kind.value,
                    "llm.model": request.model or self.default_model,
                    "llm.task": task_attr,
                    "llm.stream": request.stream,
                },
            ):
                response = await self._inner.complete(request)
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            record_llm_request(
                provider=self.provider_kind.value,
                task=task_attr,
                duration_seconds=latency_ms / 1000,
                outcome="error",
            )
            raise
        if response.usage.has_usage:
            set_span_attributes(
                {
                    "llm.prompt_tokens": response.usage.prompt_tokens,
                    "llm.completion_tokens": response.usage.completion_tokens,
                    "llm.total_tokens": response.usage.total_tokens,
                },
            )
        latency_ms = (time.perf_counter() - started) * 1000
        record_llm_request(
            provider=self.provider_kind.value,
            task=task_attr,
            duration_seconds=latency_ms / 1000,
            outcome="success",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        if self._should_log():
            self._audit.log_llm_usage(
                build_llm_usage_from_response(
                    request=request,
                    response=response,
                    latency_ms=latency_ms,
                    stream=request.stream,
                ),
            )
        return response

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        task = request.metadata.get("task")
        task_attr = task if isinstance(task, str) else None
        started = time.perf_counter()
        collected: list[LLMStreamChunk] = []
        try:
            with start_span(
                "insightai.llm",
                attributes={
                    "llm.provider": self.provider_kind.value,
                    "llm.model": request.model or self.default_model,
                    "llm.task": task_attr,
                    "llm.stream": True,
                },
            ):
                async for chunk in self._inner.complete_stream(request):
                    collected.append(chunk)
                    yield chunk
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            record_llm_request(
                provider=self.provider_kind.value,
                task=task_attr,
                duration_seconds=latency_ms / 1000,
                outcome="error",
            )
            raise
        usage, finish_reason = terminal_stream_usage(collected)
        if usage.has_usage:
            set_span_attributes(
                {
                    "llm.prompt_tokens": usage.prompt_tokens,
                    "llm.completion_tokens": usage.completion_tokens,
                    "llm.total_tokens": usage.total_tokens,
                },
            )
        latency_ms = (time.perf_counter() - started) * 1000
        record_llm_request(
            provider=self.provider_kind.value,
            task=task_attr,
            duration_seconds=latency_ms / 1000,
            outcome="success",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        if self._should_log():
            model = request.model or self.default_model
            self._audit.log_llm_usage(
                build_llm_usage_record(
                    request=request,
                    provider=self.provider_kind.value,
                    model=model,
                    usage=usage,
                    latency_ms=latency_ms,
                    stream=True,
                    finish_reason=finish_reason,
                ),
            )

    async def health_check(self) -> bool:
        return await self._inner.health_check()

    def _should_log(self) -> bool:
        return (
            self._settings.observability_audit_enabled
            and self._settings.observability_llm_usage_enabled
        )
