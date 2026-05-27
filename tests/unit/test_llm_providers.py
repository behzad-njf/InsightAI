"""Unit tests for LLM providers and AI factory (mocked SDKs)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from insightai.domain.models.llm import (
    AIFrameworkKind,
    LLMMessage,
    LLMProviderKind,
    LLMRequest,
    LLMRole,
    join_stream_text,
)
from insightai.infrastructure.ai.factory import (
    build_ai_components,
    create_ai_framework,
    create_llm_provider,
    create_sql_generator,
)
from insightai.infrastructure.ai.frameworks.langchain_adapter import LangChainFrameworkAdapter
from insightai.infrastructure.ai.providers.groq_provider import GroqLLMProvider
from insightai.infrastructure.ai.providers.observing_provider import ObservingLLMProvider
from insightai.infrastructure.ai.providers.openai_provider import OpenAILLMProvider
from insightai.infrastructure.ai.providers.openrouter_provider import OpenRouterLLMProvider
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type,call-arg]


def _stream_event(
    *,
    text: str | None = None,
    finish_reason: str | None = None,
    usage: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=text),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def _groq_completion(content: str = "Hello from Groq") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


@pytest.mark.asyncio
async def test_groq_provider_complete() -> None:
    settings = _settings(groq_api_key="gsk-test", groq_model="llama-3.3-70b-versatile")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _groq_completion()

    with patch(
        "insightai.infrastructure.ai.providers.groq_provider.Groq",
        return_value=mock_client,
    ):
        provider = GroqLLMProvider(settings)
        response = await provider.complete(
            LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="Hi")]),
        )

    assert response.content == "Hello from Groq"
    assert response.provider == LLMProviderKind.GROQ
    assert response.usage.total_tokens == 15
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_groq_stream_fallback_to_non_stream() -> None:
    settings = _settings(groq_api_key="gsk-test")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("stream failed"),
        _groq_completion("fallback"),
    ]

    with patch(
        "insightai.infrastructure.ai.providers.groq_provider.Groq",
        return_value=mock_client,
    ):
        provider = GroqLLMProvider(settings)
        response = await provider.complete(
            LLMRequest(
                messages=[LLMMessage(role=LLMRole.USER, content="Hi")],
                stream=True,
            ),
        )

    assert response.content == "fallback"
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_groq_provider_complete_stream_yields_chunks() -> None:
    settings = _settings(groq_api_key="gsk-test")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(
        [
            _stream_event(text="Hel"),
            _stream_event(text="lo"),
            _stream_event(
                finish_reason="stop",
                usage=SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                ),
            ),
        ]
    )

    with patch(
        "insightai.infrastructure.ai.providers.groq_provider.Groq",
        return_value=mock_client,
    ):
        provider = GroqLLMProvider(settings)
        chunks = [c async for c in provider.complete_stream(_user_request())]

    assert join_stream_text(chunks) == "Hello"
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == 3
    mock_client.chat.completions.create.assert_called_once()
    assert mock_client.chat.completions.create.call_args.kwargs["stream"] is True


@pytest.mark.asyncio
async def test_openai_provider_complete_stream_yields_chunks() -> None:
    settings = _settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")

    async def mock_stream():
        yield _stream_event(text="A")
        yield _stream_event(text="B")
        yield _stream_event(finish_reason="stop")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

    with patch(
        "insightai.infrastructure.ai.providers.openai_provider.AsyncOpenAI",
        return_value=mock_client,
    ):
        provider = OpenAILLMProvider(settings)
        chunks = [c async for c in provider.complete_stream(_user_request())]

    assert join_stream_text(chunks) == "AB"
    assert chunks[-1].finish_reason == "stop"
    mock_client.chat.completions.create.assert_awaited_once()
    assert mock_client.chat.completions.create.await_args.kwargs["stream"] is True


@pytest.mark.asyncio
async def test_openai_provider_complete() -> None:
    settings = _settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    mock_completion = _groq_completion("Hello from OpenAI")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch(
        "insightai.infrastructure.ai.providers.openai_provider.AsyncOpenAI",
        return_value=mock_client,
    ):
        provider = OpenAILLMProvider(settings)
        response = await provider.complete(
            LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="Hi")]),
        )

    assert response.content == "Hello from OpenAI"
    assert response.provider == LLMProviderKind.OPENAI


@pytest.mark.asyncio
async def test_openrouter_provider_complete() -> None:
    settings = _settings(
        openrouter_api_key="sk-or-test",
        openrouter_model="openai/gpt-4o-mini",
    )
    mock_client = MagicMock()
    mock_client.chat.send.return_value = _groq_completion("Hello from OpenRouter")

    with patch(
        "insightai.infrastructure.ai.providers.openrouter_provider.OpenRouter",
        return_value=mock_client,
    ):
        provider = OpenRouterLLMProvider(settings)
        response = await provider.complete(
            LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="Hi")]),
        )

    assert response.content == "Hello from OpenRouter"
    assert response.provider == LLMProviderKind.OPENROUTER
    mock_client.chat.send.assert_called_once()
    call_kwargs = mock_client.chat.send.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-4o-mini"
    assert call_kwargs["stream"] is False
    assert call_kwargs["x_open_router_title"] == "InsightAI"


def test_factory_selects_openrouter() -> None:
    settings = _settings(
        llm_provider=LLMProviderKind.OPENROUTER,
        openrouter_api_key="sk-or-test",
    )
    with patch(
        "insightai.infrastructure.ai.providers.openrouter_provider.OpenRouter",
        return_value=MagicMock(),
    ):
        provider = create_llm_provider(settings)
    assert isinstance(provider, ObservingLLMProvider)
    assert isinstance(provider._inner, OpenRouterLLMProvider)  # noqa: SLF001


def test_factory_selects_groq() -> None:
    settings = _settings(
        llm_provider=LLMProviderKind.GROQ,
        groq_api_key="gsk-test",
    )
    with patch(
        "insightai.infrastructure.ai.providers.groq_provider.Groq",
        return_value=MagicMock(),
    ):
        provider = create_llm_provider(settings)
    assert isinstance(provider, ObservingLLMProvider)
    assert isinstance(provider._inner, GroqLLMProvider)  # noqa: SLF001


def test_factory_selects_openai() -> None:
    settings = _settings(
        llm_provider=LLMProviderKind.OPENAI,
        openai_api_key="sk-test",
    )
    with patch(
        "insightai.infrastructure.ai.providers.openai_provider.AsyncOpenAI",
        return_value=MagicMock(),
    ):
        provider = create_llm_provider(settings)
    assert isinstance(provider, ObservingLLMProvider)
    assert isinstance(provider._inner, OpenAILLMProvider)  # noqa: SLF001


def test_llamaindex_framework_delegates() -> None:
    settings = _settings(
        llm_provider=LLMProviderKind.GROQ,
        groq_api_key="gsk-test",
        ai_framework=AIFrameworkKind.LLAMAINDEX,
    )
    mock_provider = MagicMock()
    mock_provider.provider_kind = LLMProviderKind.GROQ

    with (
        patch("llama_index.llms.openai.OpenAI", return_value=MagicMock()),
        patch("llama_index.core.Settings"),
    ):
        framework = create_ai_framework(mock_provider, settings)

    assert framework.framework_kind == AIFrameworkKind.LLAMAINDEX
    assert framework.get_llm_provider() is mock_provider


@pytest.mark.asyncio
async def test_langchain_adapter_delegates_complete() -> None:
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value=MagicMock())
    settings = _settings(groq_api_key="gsk-test")
    framework = LangChainFrameworkAdapter(mock_provider, settings)
    await framework.complete(_user_request())
    mock_provider.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_langchain_adapter_complete_stream_delegates() -> None:
    mock_provider = MagicMock()

    async def _stream(_request: object) -> AsyncIterator[object]:
        yield MagicMock(text="hi")

    mock_provider.complete_stream = _stream
    settings = _settings(groq_api_key="gsk-test")
    framework = LangChainFrameworkAdapter(mock_provider, settings)
    chunks = [chunk async for chunk in framework.complete_stream(_user_request())]
    assert chunks


def _user_request(**kwargs: object) -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content="Hi")],
        **kwargs,  # type: ignore[arg-type]
    )


def test_build_ai_components() -> None:
    settings = _settings(
        llm_provider=LLMProviderKind.GROQ,
        groq_api_key="gsk-test",
        ai_framework=AIFrameworkKind.LLAMAINDEX,
    )
    with (
        patch(
            "insightai.infrastructure.ai.providers.groq_provider.Groq",
            return_value=MagicMock(),
        ),
        patch("llama_index.llms.openai.OpenAI", return_value=MagicMock()),
        patch("llama_index.core.Settings"),
    ):
        components = build_ai_components(settings)

    assert components.llm_provider.provider_kind == LLMProviderKind.GROQ
    assert components.framework.framework_kind == AIFrameworkKind.LLAMAINDEX
    assert components.sql_generator is not None
    assert components.answer_generator is not None


def test_create_sql_generator() -> None:
    settings = _settings(groq_api_key="gsk-test", ai_framework=AIFrameworkKind.LLAMAINDEX)
    mock_framework = MagicMock()
    with patch(
        "insightai.infrastructure.ai.factory.create_ai_framework",
        return_value=mock_framework,
    ):
        generator = create_sql_generator(settings=settings)
    assert isinstance(generator, LLMSQLGenerator)


def test_invalid_llm_provider_enum_rejected_by_settings() -> None:
    with pytest.raises(ValueError):
        _settings(llm_provider="unknown")  # type: ignore[arg-type]
