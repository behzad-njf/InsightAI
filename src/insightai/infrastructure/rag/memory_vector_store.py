"""In-memory vector store for tests and offline dev (Phase 10.3)."""

from __future__ import annotations

from insightai.domain.models.rag import (
    IngestedChunkRecord,
    VectorSearchRequest,
    VectorSearchResult,
)
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.rag.vector_utils import cosine_similarity


class InMemoryVectorStore(IVectorStore):
    """Brute-force cosine search over stored chunk records."""

    def __init__(self) -> None:
        self._records: dict[str, IngestedChunkRecord] = {}
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def ensure_schema(self, dimensions: int) -> None:
        self._dimensions = dimensions

    def upsert_records(self, records: list[IngestedChunkRecord]) -> int:
        if not records:
            return 0
        dim = len(records[0].embedding)
        if self._dimensions is None:
            self._dimensions = dim
        for record in records:
            if len(record.embedding) != self._dimensions:
                msg = "All embeddings must share the same dimensions."
                raise ValueError(msg)
            self._records[record.id] = record
        return len(records)

    def search(self, request: VectorSearchRequest) -> list[VectorSearchResult]:
        if self._dimensions is None:
            return []

        scored: list[VectorSearchResult] = []
        for record in self._records.values():
            if len(record.embedding) != len(request.query_embedding):
                continue
            score = cosine_similarity(request.query_embedding, record.embedding)
            if request.min_score is not None and score < request.min_score:
                continue
            scored.append(
                VectorSearchResult(
                    id=record.id,
                    source_path=record.source_path,
                    chunk_index=record.chunk_index,
                    text=record.text,
                    score=score,
                    title=record.title,
                    section=record.section,
                    metadata=dict(record.metadata),
                ),
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: request.top_k]

    def delete_all(self) -> None:
        self._records.clear()

    def count(self) -> int:
        return len(self._records)
