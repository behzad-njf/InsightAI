"""Vector store port for RAG retrieval (Phase 10.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.rag import (
        IngestedChunkRecord,
        VectorSearchRequest,
        VectorSearchResult,
    )


class IVectorStore(ABC):
    """
    Persist and search document chunk embeddings.

    Implementations: PostgreSQL + pgvector (production), in-memory (tests).
    """

    @property
    @abstractmethod
    def dimensions(self) -> int | None:
        """Configured vector width after ``ensure_schema`` or first upsert."""

    @abstractmethod
    def ensure_schema(self, dimensions: int) -> None:
        """Create extension/table/index when using a database backend."""

    @abstractmethod
    def upsert_records(self, records: list[IngestedChunkRecord]) -> int:
        """Insert or update chunks by ``id``. Returns number of rows written."""

    @abstractmethod
    def search(self, request: VectorSearchRequest) -> list[VectorSearchResult]:
        """
        Return the closest chunks to ``request.query_embedding`` (cosine similarity).

        Results are ordered by descending similarity score.
        """

    @abstractmethod
    def delete_all(self) -> None:
        """Remove all stored chunks (used before full re-load)."""

    @abstractmethod
    def count(self) -> int:
        """Number of chunks currently stored."""
