"""Unit tests for vector stores (Phase 10.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.models.embedding import EmbeddingRequest
from insightai.domain.models.rag import (
    DocumentIngestOptions,
    IngestedChunkRecord,
    VectorSearchRequest,
)
from insightai.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from insightai.infrastructure.rag.ingest import DocumentIngestService
from insightai.infrastructure.rag.load_vectors import VectorIndexLoadService
from insightai.infrastructure.rag.memory_vector_store import InMemoryVectorStore
from insightai.infrastructure.rag.vector_bootstrap import create_vector_store
from insightai.infrastructure.rag.vector_utils import cosine_similarity
from tests.conftest import make_settings

FIXTURES_DIR = Path("tests/fixtures/rag")


@pytest.mark.asyncio
async def test_memory_vector_store_search_orders_by_similarity() -> None:
    store = InMemoryVectorStore()
    store.ensure_schema(4)
    store.upsert_records(
        [
            _record("a", [1.0, 0.0, 0.0, 0.0], text="alpha"),
            _record("b", [0.0, 1.0, 0.0, 0.0], text="beta"),
        ],
    )

    hits = store.search(
        VectorSearchRequest(query_embedding=[0.9, 0.1, 0.0, 0.0], top_k=2),
    )
    assert len(hits) == 2
    assert hits[0].text == "alpha"
    assert hits[0].score >= hits[1].score


@pytest.mark.asyncio
async def test_load_jsonl_into_memory_vector_store(tmp_path: Path) -> None:
    settings = make_settings()
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=32,
    )
    output = tmp_path / "chunks.jsonl"

    ingest = DocumentIngestService(provider, settings)
    await ingest.ingest(
        DocumentIngestOptions(
            input_path=FIXTURES_DIR / "campus_overview.md",
            output_path=output,
            chunk_size=400,
            chunk_overlap=40,
        ),
    )

    query = await provider.embed(EmbeddingRequest(texts=["classrooms and children"]))
    store = InMemoryVectorStore()
    loader = VectorIndexLoadService(store)
    result = loader.load_jsonl(output, clear_existing=True)
    hits = store.search(
        VectorSearchRequest(query_embedding=query.vector_values[0], top_k=3),
    )
    assert hits
    assert any("classroom" in hit.text.lower() for hit in hits)

    assert result.records_loaded > 0
    assert store.count() == result.records_loaded


def test_create_vector_store_memory_backend() -> None:
    settings = make_settings(rag_vector_backend="memory")
    store = create_vector_store(settings)
    assert isinstance(store, InMemoryVectorStore)


def test_cosine_similarity_identical_vectors() -> None:
    vec = [0.1, 0.2, 0.3]
    assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=0.001)


def _record(chunk_id: str, embedding: list[float], *, text: str) -> IngestedChunkRecord:
    return IngestedChunkRecord(
        id=chunk_id,
        source_path="/docs/example.md",
        chunk_index=0,
        text=text,
        embedding=embedding,
    )
