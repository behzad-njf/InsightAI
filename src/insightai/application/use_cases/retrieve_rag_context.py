"""Retrieve document context from the vector store (Phase 10.4)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from insightai.domain.models.embedding import EmbeddingRequest
from insightai.domain.models.hybrid import RAGRetrievalResult, RAGSourceCitation
from insightai.domain.models.rag import VectorSearchRequest

if TYPE_CHECKING:
    from insightai.domain.ports.embedding_provider import IEmbeddingProvider
    from insightai.domain.ports.vector_store import IVectorStore
    from insightai.infrastructure.config.settings import Settings


class RetrieveRAGContextUseCase:
    """Embed the user question and run vector similarity search."""

    def __init__(
        self,
        embedding_provider: IEmbeddingProvider,
        vector_store: IVectorStore,
        settings: Settings | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._embeddings = embedding_provider
        self._store = vector_store
        self._settings = settings or get_settings()

    async def execute(
        self,
        question: str,
        *,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RAGRetrievalResult:
        started = time.perf_counter()
        resolved_top_k = top_k if top_k is not None else self._settings.rag_search_top_k
        resolved_min = (
            min_score if min_score is not None else self._settings.rag_search_min_score
        )

        embedding = await self._embeddings.embed(
            EmbeddingRequest(texts=[question.strip()]),
        )
        query_vector = embedding.vector_values[0]

        hits = self._store.search(
            VectorSearchRequest(
                query_embedding=query_vector,
                top_k=resolved_top_k,
                min_score=resolved_min,
            ),
        )
        sources = [RAGSourceCitation.from_search_result(hit) for hit in hits]
        retrieval_ms = (time.perf_counter() - started) * 1000

        return RAGRetrievalResult(
            question=question.strip(),
            sources=sources,
            top_k=resolved_top_k,
            retrieval_ms=round(retrieval_ms, 2),
        )
