"""Unit tests for LLM streaming domain types and ports (Step 1)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from insightai.domain.models.llm import (
    LLMMessage,
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMRole,
    LLMStreamChunk,
    TokenUsage,
    join_stream_text,
)
from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.llm_provider import ILLMProvider


class _FakeStreamProvider(ILLMProvider):
    @property
    def provider_kind(self) -> LLMProviderKind:
        return LLMProviderKind.OPENAI

    @property
    def default_model(self) -> str:
        return "fake-model"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="full",
            model="fake-model",
            provider=LLMProviderKind.OPENAI,
        )

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        yield LLMStreamChunk(text="Hel")
        yield LLMStreamChunk(text="lo")
        yield LLMStreamChunk(finish_reason="stop", usage=TokenUsage(completion_tokens=2))


class _FakeFramework(IAIFramework):
    def __init__(self, provider: ILLMProvider) -> None:
        self._provider = provider

    @property
    def framework_kind(self):
        from insightai.domain.models.llm import AIFrameworkKind

        return AIFrameworkKind.LLAMAINDEX

    def get_llm_provider(self) -> ILLMProvider:
        return self._provider

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._provider.complete(request)


@pytest.mark.asyncio
async def test_join_stream_text() -> None:
    chunks = [
        LLMStreamChunk(text="a"),
        LLMStreamChunk(text="b"),
        LLMStreamChunk(finish_reason="stop"),
    ]
    assert join_stream_text(chunks) == "ab"


@pytest.mark.asyncio
async def test_provider_complete_stream_override() -> None:
    provider = _FakeStreamProvider()
    chunks = [c async for c in provider.complete_stream(_request())]
    assert join_stream_text(chunks) == "Hello"
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.completion_tokens == 2


@pytest.mark.asyncio
async def test_provider_complete_stream_default_from_complete() -> None:
    class _SingleShot(ILLMProvider):
        @property
        def provider_kind(self) -> LLMProviderKind:
            return LLMProviderKind.GROQ

        @property
        def default_model(self) -> str:
            return "m"

        async def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                content="done",
                model="m",
                provider=LLMProviderKind.GROQ,
                usage=TokenUsage(total_tokens=1),
                finish_reason="stop",
            )

    chunks = [c async for c in _SingleShot().complete_stream(_request())]
    assert join_stream_text(chunks) == "done"
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None


@pytest.mark.asyncio
async def test_framework_complete_stream_delegates_to_provider() -> None:
    provider = _FakeStreamProvider()
    framework = _FakeFramework(provider)
    chunks = [c async for c in framework.complete_stream(_request())]
    assert join_stream_text(chunks) == "Hello"


def _request() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="hi")])
