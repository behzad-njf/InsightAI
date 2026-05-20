"""RAG infrastructure bootstrap (Phase 10.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from insightai.domain.exceptions import ConfigurationError, VectorStoreConfigurationError
from insightai.domain.ports.embedding_provider import IEmbeddingProvider
from insightai.domain.ports.query_router import IQueryRouter
from insightai.domain.ports.rag_answer_generator import IRAGAnswerGenerator
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.embeddings.factory import create_embedding_provider
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.heuristic_router import HeuristicQueryRouter
from insightai.infrastructure.rag.rag_answer_generator import LLMRAGAnswerGenerator
from insightai.infrastructure.rag.vector_bootstrap import create_vector_store

logger = get_logger(__name__)


class RAGRouterMode(StrEnum):
    HEURISTIC = "heuristic"


@dataclass(frozen=True)
class RAGComponents:
    """Bundled RAG services for hybrid ask (Phase 10.4)."""

    settings: Settings
    enabled: bool
    embedding_provider: IEmbeddingProvider | None
    vector_store: IVectorStore | None
    query_router: IQueryRouter | None
    rag_answer_generator: IRAGAnswerGenerator | None


def create_query_router(settings: Settings) -> IQueryRouter:
    mode = settings.rag_router_mode.lower()
    if mode == RAGRouterMode.HEURISTIC:
        return HeuristicQueryRouter()
    msg = f"Unsupported RAG router mode: {settings.rag_router_mode}"
    raise ConfigurationError(msg)


def build_rag_components(settings: Settings | None = None) -> RAGComponents:
    """
    Build embedding, vector store, router, and RAG answer generator when enabled.

    When ``INSIGHTAI_RAG_ENABLED=false``, returns disabled components (SQL-only ask).
    """
    settings = settings or get_settings()
    if not settings.rag_enabled:
        logger.info("rag_disabled")
        return RAGComponents(
            settings=settings,
            enabled=False,
            embedding_provider=None,
            vector_store=None,
            query_router=None,
            rag_answer_generator=None,
        )

    try:
        embedding_provider = create_embedding_provider(settings)
        vector_store = create_vector_store(settings)
        query_router = create_query_router(settings)
    except (ConfigurationError, VectorStoreConfigurationError) as exc:
        logger.warning("rag_components_unavailable", error=str(exc))
        return RAGComponents(
            settings=settings,
            enabled=False,
            embedding_provider=None,
            vector_store=None,
            query_router=None,
            rag_answer_generator=None,
        )

    from insightai.infrastructure.ai.factory import create_ai_framework

    framework = create_ai_framework(settings=settings)
    rag_answer_generator = LLMRAGAnswerGenerator(framework, settings)

    logger.info(
        "rag_components_configured",
        vector_backend=settings.rag_vector_backend,
        router_mode=settings.rag_router_mode,
    )
    return RAGComponents(
        settings=settings,
        enabled=True,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        query_router=query_router,
        rag_answer_generator=rag_answer_generator,
    )
