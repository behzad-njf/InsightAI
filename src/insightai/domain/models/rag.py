"""RAG document models (Phase 10.2)."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from insightai.domain.models.embedding import EmbeddingProviderKind  # noqa: TC001


class DocumentChunk(BaseModel):
    """A text segment ready for embedding."""

    source_path: str
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    title: str | None = None
    section: str | None = None

    model_config = {"frozen": True}


class IngestedChunkRecord(BaseModel):
    """Persisted chunk with embedding (JSONL row)."""

    id: str
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None
    section: str | None = None
    embedding: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class RAGIndexManifest(BaseModel):
    """Metadata written beside the JSONL index (``manifest.json``)."""

    version: int = 1
    provider: EmbeddingProviderKind
    model: str
    dimensions: int
    chunk_count: int = Field(ge=0)
    source_files: list[str] = Field(default_factory=list)
    output_path: str
    created_at: datetime
    chunk_size: int
    chunk_overlap: int

    model_config = {"frozen": True}


class DocumentIngestResult(BaseModel):
    """Summary returned by the ingest pipeline."""

    manifest: RAGIndexManifest
    chunks_written: int
    files_processed: int
    files_skipped: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class VectorSearchRequest(BaseModel):
    """Similarity search input."""

    query_embedding: list[float] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional cosine similarity floor.",
    )

    model_config = {"frozen": True}


class VectorSearchResult(BaseModel):
    """One retrieved chunk with similarity score."""

    id: str
    source_path: str
    chunk_index: int
    text: str
    score: float = Field(ge=0.0, le=1.0)
    title: str | None = None
    section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class VectorLoadResult(BaseModel):
    """Outcome of loading a JSONL index into a vector store."""

    records_loaded: int
    dimensions: int
    table_or_store: str
    cleared_existing: bool

    model_config = {"frozen": True}


class DocumentIngestOptions(BaseModel):
    """Runtime options for document ingestion."""

    input_path: Path
    output_path: Path
    recursive: bool = True
    dry_run: bool = False
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=2000)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            msg = "chunk_overlap must be smaller than chunk_size."
            raise ValueError(msg)
        return self
