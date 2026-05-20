"""Document ingestion pipeline (Phase 10.2)."""

from __future__ import annotations

import hashlib

from insightai.domain.models.embedding import EmbeddingRequest
from insightai.domain.models.rag import (
    DocumentChunk,
    DocumentIngestOptions,
    DocumentIngestResult,
    IngestedChunkRecord,
    RAGIndexManifest,
)
from insightai.domain.ports.embedding_provider import IEmbeddingProvider
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.chunking import chunk_document_text
from insightai.infrastructure.rag.index_store import utc_now, write_jsonl_index, write_manifest
from insightai.infrastructure.rag.loaders import (
    DocumentLoadError,
    discover_document_paths,
    load_document_text,
)

logger = get_logger(__name__)


class DocumentIngestService:
    """Chunk documents, embed them, and write a local JSONL index."""

    def __init__(
        self,
        embedding_provider: IEmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._embeddings = embedding_provider
        self._settings = settings

    async def ingest(self, options: DocumentIngestOptions) -> DocumentIngestResult:
        paths = discover_document_paths(
            options.input_path,
            recursive=options.recursive,
        )
        if not paths:
            msg = f"No supported documents found under {options.input_path}"
            raise ValueError(msg)

        all_chunks: list[DocumentChunk] = []
        source_files: list[str] = []
        skipped: list[str] = []

        for path in paths:
            try:
                text, title = load_document_text(path)
            except (DocumentLoadError, OSError, UnicodeDecodeError) as exc:
                logger.warning("document_load_skipped", path=str(path), error=str(exc))
                skipped.append(str(path))
                continue

            chunks = chunk_document_text(
                source_path=str(path.resolve()),
                text=text,
                title=title,
                chunk_size=options.chunk_size,
                chunk_overlap=options.chunk_overlap,
            )
            if not chunks:
                skipped.append(str(path))
                continue

            all_chunks.extend(chunks)
            source_files.append(str(path.resolve()))

        if not all_chunks:
            msg = "No chunks produced from input documents."
            raise ValueError(msg)

        logger.info(
            "rag_ingest_chunks_prepared",
            files=len(source_files),
            chunks=len(all_chunks),
            dry_run=options.dry_run,
        )

        if options.dry_run:
            manifest = self._build_manifest(
                options=options,
                chunk_count=len(all_chunks),
                source_files=source_files,
            )
            return DocumentIngestResult(
                manifest=manifest,
                chunks_written=0,
                files_processed=len(source_files),
                files_skipped=skipped,
            )

        records = await self._embed_chunks(all_chunks)
        output_path = options.output_path.resolve()
        write_jsonl_index(output_path, records)
        manifest = self._build_manifest(
            options=options,
            chunk_count=len(records),
            source_files=source_files,
        )
        write_manifest(output_path, manifest)

        logger.info(
            "rag_ingest_complete",
            output=str(output_path),
            chunks=len(records),
            manifest=str(output_path.with_name("manifest.json")),
        )

        return DocumentIngestResult(
            manifest=manifest,
            chunks_written=len(records),
            files_processed=len(source_files),
            files_skipped=skipped,
        )

    async def _embed_chunks(self, chunks: list[DocumentChunk]) -> list[IngestedChunkRecord]:
        batch_size = self._settings.embedding_max_batch_size
        records: list[IngestedChunkRecord] = []

        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            result = await self._embeddings.embed(
                EmbeddingRequest(texts=[chunk.text for chunk in batch]),
            )
            vectors = result.vector_values
            for chunk, vector in zip(batch, vectors, strict=True):
                records.append(
                    IngestedChunkRecord(
                        id=_chunk_id(chunk),
                        source_path=chunk.source_path,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        title=chunk.title,
                        section=chunk.section,
                        embedding=vector,
                        metadata={
                            "dimensions": len(vector),
                            "embedding_model": result.model,
                        },
                    ),
                )

        return records

    def _build_manifest(
        self,
        *,
        options: DocumentIngestOptions,
        chunk_count: int,
        source_files: list[str],
    ) -> RAGIndexManifest:
        return RAGIndexManifest(
            provider=self._embeddings.provider_kind,
            model=self._embeddings.default_model,
            dimensions=self._embeddings.dimensions,
            chunk_count=chunk_count,
            source_files=source_files,
            output_path=str(options.output_path.resolve()),
            created_at=utc_now(),
            chunk_size=options.chunk_size,
            chunk_overlap=options.chunk_overlap,
        )


def _chunk_id(chunk: DocumentChunk) -> str:
    fingerprint = (
        f"{chunk.source_path}|{chunk.chunk_index}|{chunk.section or ''}|{chunk.text[:200]}"
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()
