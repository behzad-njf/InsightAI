"""Embedding provider port (Phase 10.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.embedding import (
        EmbeddingProviderKind,
        EmbeddingRequest,
        EmbeddingResult,
    )


class IEmbeddingProvider(ABC):
    """
    Generate dense vectors for document chunks and queries (RAG / pgvector).

    Implementations must preserve input order in ``EmbeddingResult.vectors``.
    """

    @property
    @abstractmethod
    def provider_kind(self) -> EmbeddingProviderKind:
        """Provider identifier (openai, local, ...)."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default embedding model from configuration."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality produced by this provider."""

    @abstractmethod
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """
        Embed one or more texts in a single provider call.

        Raises:
            EmbeddingProviderError: Provider returned an error response.
            EmbeddingProviderUnavailableError: Network or rate-limit failure.
            EmbeddingConfigurationError: Missing credentials or invalid config.
        """
