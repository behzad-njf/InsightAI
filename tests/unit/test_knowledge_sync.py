"""Knowledge folder startup sync tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from insightai.infrastructure.rag.knowledge_sync import sync_knowledge_on_startup
from insightai.infrastructure.rag.memory_vector_store import InMemoryVectorStore
from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_sync_knowledge_ingests_and_loads_vectors(tmp_path: Path) -> None:
    knowledge = tmp_path / "Knowledge"
    knowledge.mkdir()
    (knowledge / "about.md").write_text(
        "# About\n\nInsightAI answers business questions from documents and SQL.\n",
        encoding="utf-8",
    )

    index_path = tmp_path / "data" / "rag_index" / "chunks.jsonl"
    settings = make_settings(
        rag_sync_knowledge_on_startup=True,
        rag_sync_knowledge_force=False,
        rag_knowledge_path=knowledge,
        rag_default_index_path=index_path,
        rag_chunk_size=200,
        rag_chunk_overlap=20,
        embedding_provider="local",
        embedding_dimensions=32,
    )
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=32,
    )
    store = InMemoryVectorStore()
    store.ensure_schema(32)

    result = await sync_knowledge_on_startup(
        settings=settings,
        embedding_provider=provider,
        vector_store=store,
    )

    assert result is not None
    assert result.documents_found == 1
    assert result.chunks_written >= 1
    assert result.records_loaded >= 1
    assert store.count() >= 1
    assert index_path.is_file()


@pytest.mark.asyncio
async def test_sync_skips_when_disabled(tmp_path: Path) -> None:
    knowledge = tmp_path / "Knowledge"
    knowledge.mkdir()
    (knowledge / "note.txt").write_text("hello", encoding="utf-8")

    settings = make_settings(
        rag_sync_knowledge_on_startup=False,
        rag_knowledge_path=knowledge,
    )
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=32,
    )
    store = InMemoryVectorStore()
    store.ensure_schema(32)

    result = await sync_knowledge_on_startup(
        settings=settings,
        embedding_provider=provider,
        vector_store=store,
    )

    assert result is None
    assert store.count() == 0


@pytest.mark.asyncio
async def test_sync_skips_when_store_already_populated(tmp_path: Path) -> None:
    knowledge = tmp_path / "Knowledge"
    knowledge.mkdir()
    (knowledge / "doc.md").write_text("# Doc\n\ncontent\n", encoding="utf-8")

    settings = make_settings(
        rag_sync_knowledge_on_startup=True,
        rag_sync_knowledge_force=False,
        rag_knowledge_path=knowledge,
        rag_default_index_path=tmp_path / "chunks.jsonl",
        embedding_provider="local",
        embedding_dimensions=32,
    )
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=32,
    )
    store = InMemoryVectorStore()
    store.ensure_schema(32)

    from insightai.domain.models.rag import IngestedChunkRecord

    store.upsert_records(
        [
            IngestedChunkRecord(
                id="seed",
                text="existing",
                embedding=[0.1] * 32,
                source_path="seed.md",
                chunk_index=0,
            ),
        ],
    )
    assert store.count() == 1

    result = await sync_knowledge_on_startup(
        settings=settings,
        embedding_provider=provider,
        vector_store=store,
    )

    assert result is None
    assert store.count() == 1
