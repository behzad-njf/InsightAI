"""Unit tests for embedding providers (Phase 10.1)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from insightai.domain.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from insightai.domain.models.embedding import EmbeddingProviderKind, EmbeddingRequest
from insightai.infrastructure.embeddings.factory import create_embedding_provider
from insightai.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from insightai.infrastructure.embeddings.openai_provider import OpenAIEmbeddingProvider
from tests.conftest import make_settings


def _embedding_response(*vectors: list[float]) -> SimpleNamespace:
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=values)
            for index, values in enumerate(vectors)
        ],
        usage=SimpleNamespace(prompt_tokens=10, total_tokens=10),
    )


@pytest.mark.asyncio
async def test_local_embedding_is_deterministic() -> None:
    provider = LocalEmbeddingProvider(model="deterministic-hash-v1", dimensions=32)
    request = EmbeddingRequest(texts=["CampusMetrics overview", "CampusMetrics overview"])
    result = await provider.embed(request)

    assert result.provider == EmbeddingProviderKind.LOCAL
    assert result.dimensions == 32
    assert len(result.vectors) == 2
    assert result.vector_values[0] == result.vector_values[1]


@pytest.mark.asyncio
async def test_local_embedding_differs_for_different_text() -> None:
    provider = LocalEmbeddingProvider(model="deterministic-hash-v1", dimensions=32)
    result = await provider.embed(
        EmbeddingRequest(texts=["question A", "question B"]),
    )
    assert result.vector_values[0] != result.vector_values[1]


@pytest.mark.asyncio
async def test_openai_embedding_provider_parses_response() -> None:
    settings = make_settings(
        openai_api_key="sk-test",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    provider = OpenAIEmbeddingProvider(settings)

    mock_response = _embedding_response([0.1, 0.2, 0.3], [0.4, 0.5, 0.6])
    with patch.object(
        provider._client.embeddings,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await provider.embed(EmbeddingRequest(texts=["doc one", "doc two"]))

    assert result.provider == EmbeddingProviderKind.OPENAI
    assert result.model == "text-embedding-3-small"
    assert result.dimensions == 3
    assert result.usage.total_tokens == 10
    assert len(result.vector_values) == 2


@pytest.mark.asyncio
async def test_openai_embedding_rejects_oversized_batch() -> None:
    settings = make_settings(
        openai_api_key="sk-test",
        embedding_provider="openai",
        embedding_max_batch_size=2,
    )
    provider = OpenAIEmbeddingProvider(settings)

    with pytest.raises(EmbeddingProviderError, match="batch size"):
        await provider.embed(EmbeddingRequest(texts=["a", "b", "c"]))


def test_factory_creates_local_provider_by_default() -> None:
    settings = make_settings()
    provider = create_embedding_provider(settings)
    assert isinstance(provider, LocalEmbeddingProvider)
    assert provider.provider_kind == EmbeddingProviderKind.LOCAL


def test_factory_creates_openai_provider() -> None:
    settings = make_settings(
        openai_api_key="sk-test",
        embedding_provider="openai",
    )
    provider = create_embedding_provider(settings)
    assert isinstance(provider, OpenAIEmbeddingProvider)


def test_factory_rejects_unknown_provider() -> None:
    settings = make_settings(embedding_provider="unknown")
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_provider(settings)


def test_embedding_request_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EmbeddingRequest(texts=["   "])
