"""Factory for embedding providers (Phase 10.1)."""

from __future__ import annotations

from insightai.domain.exceptions import EmbeddingConfigurationError
from insightai.domain.models.embedding import EmbeddingProviderKind
from insightai.domain.ports.embedding_provider import IEmbeddingProvider
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from insightai.infrastructure.embeddings.openai_provider import OpenAIEmbeddingProvider
from insightai.infrastructure.logging.setup import get_logger

logger = get_logger(__name__)


def create_embedding_provider(settings: Settings | None = None) -> IEmbeddingProvider:
    """
    Instantiate the configured embedding provider.

    Uses ``INSIGHTAI_EMBEDDING_PROVIDER`` (``openai`` | ``local``).
    """
    settings = settings or get_settings()
    try:
        kind = EmbeddingProviderKind(settings.embedding_provider.lower())
    except ValueError as exc:
        msg = f"Unsupported embedding provider: {settings.embedding_provider}"
        raise EmbeddingConfigurationError(msg) from exc

    if kind == EmbeddingProviderKind.OPENAI:
        openai_provider = OpenAIEmbeddingProvider(settings)
        logger.info(
            "embedding_provider_configured",
            kind="openai",
            model=openai_provider.default_model,
            dimensions=openai_provider.dimensions,
        )
        return openai_provider

    if kind == EmbeddingProviderKind.LOCAL:
        local_provider = LocalEmbeddingProvider(
            model=settings.embedding_local_model,
            dimensions=settings.resolved_embedding_dimensions(),
        )
        logger.info(
            "embedding_provider_configured",
            kind="local",
            model=local_provider.default_model,
            dimensions=local_provider.dimensions,
        )
        return local_provider

    msg = f"Unsupported embedding provider: {settings.embedding_provider}"
    raise EmbeddingConfigurationError(msg)
