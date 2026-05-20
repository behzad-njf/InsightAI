"""Unit tests for RAG document ingestion (Phase 10.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.models.rag import DocumentIngestOptions
from insightai.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from insightai.infrastructure.rag.chunking import chunk_document_text
from insightai.infrastructure.rag.index_store import iter_index_records, load_manifest
from insightai.infrastructure.rag.ingest import DocumentIngestService
from insightai.infrastructure.rag.loaders import discover_document_paths, load_document_text
from tests.conftest import make_settings

FIXTURES_DIR = Path("tests/fixtures/rag")


def test_chunk_markdown_respects_sections() -> None:
    text = (FIXTURES_DIR / "campus_overview.md").read_text(encoding="utf-8")
    chunks = chunk_document_text(
        source_path="campus_overview.md",
        text=text,
        title="campus_overview",
        chunk_size=400,
        chunk_overlap=50,
    )
    assert len(chunks) >= 3
    sections = {chunk.section for chunk in chunks if chunk.section}
    assert "Classrooms" in sections
    assert "Accounts" in sections


def test_discover_document_paths_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "docs" / "nested"
    nested.mkdir(parents=True)
    (nested / "a.md").write_text("# A\n\nAlpha.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Beta text.", encoding="utf-8")

    paths = discover_document_paths(tmp_path, recursive=True)
    assert len(paths) == 2


@pytest.mark.asyncio
async def test_ingest_service_dry_run() -> None:
    settings = make_settings()
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=settings.resolved_embedding_dimensions(),
    )
    service = DocumentIngestService(provider, settings)
    result = await service.ingest(
        DocumentIngestOptions(
            input_path=FIXTURES_DIR,
            output_path=Path("data/test_rag/chunks.jsonl"),
            dry_run=True,
        ),
    )

    assert result.chunks_written == 0
    assert result.files_processed == 1
    assert result.manifest.chunk_count >= 3


@pytest.mark.asyncio
async def test_ingest_writes_jsonl_and_manifest(tmp_path: Path) -> None:
    settings = make_settings()
    provider = LocalEmbeddingProvider(
        model=settings.embedding_local_model,
        dimensions=32,
    )
    service = DocumentIngestService(provider, settings)
    output = tmp_path / "chunks.jsonl"

    result = await service.ingest(
        DocumentIngestOptions(
            input_path=FIXTURES_DIR / "campus_overview.md",
            output_path=output,
            chunk_size=300,
            chunk_overlap=40,
        ),
    )

    assert result.chunks_written == result.manifest.chunk_count
    assert output.is_file()
    manifest = load_manifest(output)
    assert manifest.dimensions == 32
    records = iter_index_records(output)
    assert len(records) == result.chunks_written
    assert all(len(record.embedding) == 32 for record in records)


def test_load_markdown_document() -> None:
    path = FIXTURES_DIR / "campus_overview.md"
    text, title = load_document_text(path)
    assert title == "campus_overview"
    assert "CampusMetrics" in text
