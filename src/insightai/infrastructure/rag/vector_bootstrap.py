"""Vector store factory (Phase 10.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.exceptions import VectorStoreConfigurationError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.database.dialect import infer_kind_from_url
from insightai.infrastructure.database.engine_factory import DatabaseConnectionFactory
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.memory_vector_store import InMemoryVectorStore

if TYPE_CHECKING:
    from insightai.infrastructure.config.settings import Settings

logger = get_logger(__name__)


def pgvector_available() -> bool:
    try:
        import pgvector  # noqa: F401
    except ImportError:
        return False
    return True


def create_vector_store(
    settings: Settings,
    *,
    backend: str | None = None,
) -> IVectorStore:
    """
    Build a vector store from settings.

    ``backend``: ``pgvector`` | ``memory`` (defaults to ``settings.rag_vector_backend``).
    """
    from insightai.infrastructure.config.settings import get_settings

    settings = settings or get_settings()
    chosen = (backend or settings.rag_vector_backend).lower()

    if chosen == "memory":
        logger.info("vector_store_configured", kind="memory")
        return InMemoryVectorStore()

    if chosen == "pgvector":
        if not pgvector_available():
            msg = "pgvector package not installed. Use: pip install 'insightai[rag]'"
            raise VectorStoreConfigurationError(msg)

        url = settings.resolve_rag_database_url()
        kind = infer_kind_from_url(url)
        if kind != DatabaseKind.POSTGRESQL:
            msg = f"RAG database must be PostgreSQL for pgvector, got: {url}"
            raise VectorStoreConfigurationError(msg)

        factory = DatabaseConnectionFactory(settings)
        config = factory.connection_config_from_url(url)
        engine = factory.create_engine(config)

        from insightai.infrastructure.rag.pgvector_store import PgVectorStore

        store = PgVectorStore(engine, settings)
        logger.info(
            "vector_store_configured",
            kind="pgvector",
            table=settings.rag_vector_table,
        )
        return store

    msg = f"Unsupported vector store backend: {chosen}"
    raise VectorStoreConfigurationError(msg)
