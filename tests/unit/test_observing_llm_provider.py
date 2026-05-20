"""Unit tests for ObservingLLMProvider (Phase 8.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.domain.models.llm import (
    LLMMessage,
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMRole,
    LLMStreamChunk,
    TokenUsage,
)
from insightai.infrastructure.ai.providers.observing_provider import ObservingLLMProvider
from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.context import bind_audit_context, clear_audit_context
from tests.conftest import make_settings

if TYPE_CHECKING:
    from insightai.domain.models.audit import LLMUsageAuditRecord


class RecordingAuditLogger:
    def __init__(self) -> None:
        self.usage: list[LLMUsageAuditRecord] = []

    def log_ask_complete(self, record: object) -> None:
        return

    def log_ask_failure(self, record: object) -> None:
        return

    def log_llm_usage(self, record: LLMUsageAuditRecord) -> None:
        self.usage.append(record)


def _request(*, stream: bool = False, task: str = "sql_generation") -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content="hi")],
        metadata={"task": task},
        stream=stream,
    )


def _response() -> LLMResponse:
    return LLMResponse(
        content="ok",
        model="test-model",
        provider=LLMProviderKind.GROQ,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        finish_reason="stop",
    )


@pytest.mark.asyncio
async def test_complete_logs_llm_usage() -> None:
    inner = MagicMock()
    inner.provider_kind = LLMProviderKind.GROQ
    inner.default_model = "test-model"
    inner.complete = AsyncMock(return_value=_response())
    audit = RecordingAuditLogger()
    settings = make_settings(
        observability_audit_enabled=True,
        observability_llm_usage_enabled=True,
    )
    provider = ObservingLLMProvider(inner, settings, audit)

    rid_token = request_id_var.set("rid-llm-1")
    audit_token = bind_audit_context(session_id="sess-9", auth_subject="user@test")
    try:
        await provider.complete(_request())
    finally:
        clear_audit_context(audit_token)
        request_id_var.reset(rid_token)

    assert len(audit.usage) == 1
    record = audit.usage[0]
    assert record.request_id == "rid-llm-1"
    assert record.session_id == "sess-9"
    assert record.auth_subject == "user@test"
    assert record.task == "sql_generation"
    assert record.total_tokens == 15
    assert record.stream is False
    assert record.latency_ms >= 0


@pytest.mark.asyncio
async def test_complete_stream_logs_usage_once_at_end() -> None:
    async def stream(_request: LLMRequest):
        yield LLMStreamChunk(text="Hel")
        yield LLMStreamChunk(text="lo")
        yield LLMStreamChunk(
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )

    inner = MagicMock()
    inner.provider_kind = LLMProviderKind.OPENAI
    inner.default_model = "gpt-test"
    inner.complete_stream = stream
    audit = RecordingAuditLogger()
    settings = make_settings(
        observability_audit_enabled=True,
        observability_llm_usage_enabled=True,
    )
    provider = ObservingLLMProvider(inner, settings, audit)

    chunks = [c async for c in provider.complete_stream(_request(stream=True, task="answer"))]
    assert len(chunks) == 3
    assert len(audit.usage) == 1
    assert audit.usage[0].task == "answer"
    assert audit.usage[0].total_tokens == 5
    assert audit.usage[0].stream is True


@pytest.mark.asyncio
async def test_llm_usage_disabled_skips_audit() -> None:
    inner = MagicMock()
    inner.provider_kind = LLMProviderKind.GROQ
    inner.default_model = "m"
    inner.complete = AsyncMock(return_value=_response())
    audit = RecordingAuditLogger()
    settings = make_settings(observability_llm_usage_enabled=False)
    provider = ObservingLLMProvider(inner, settings, audit)

    await provider.complete(_request())

    assert audit.usage == []
