"""Sync the Knowledge/ folder into the vector store on startup (Phase 10+)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightai.domain.models.rag import DocumentIngestOptions, VectorLoadResult
from insightai.domain.ports.embedding_provider import IEmbeddingProvider
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.ingest import DocumentIngestService
from insightai.infrastructure.rag.load_vectors import VectorIndexLoadService
from insightai.infrastructure.rag.loaders import discover_document_paths

logger = get_logger(__name__)


@dataclass(frozen=True)
class KnowledgeSyncResult:
    """Outcome of ingesting ``Knowledge/`` and loading the vector index."""

    knowledge_path: Path
    documents_found: int
    chunks_written: int
    records_loaded: int
    index_path: Path
    load_result: VectorLoadResult

    @property
    def skipped(self) -> bool:
        return self.documents_found == 0


async def sync_knowledge_on_startup(
    *,
    settings: Settings,
    embedding_provider: IEmbeddingProvider,
    vector_store: IVectorStore,
) -> KnowledgeSyncResult | None:
    """
    Ingest ``settings.rag_knowledge_path`` and load chunks into the vector store.

    Returns ``None`` when sync is disabled or the knowledge directory has no documents.
    """
    if not settings.rag_sync_knowledge_on_startup:
        logger.info("knowledge_sync_disabled")
        return None

    knowledge_path = settings.resolved_rag_knowledge_path()
    if not knowledge_path.is_dir():
        logger.warning("knowledge_path_missing", path=str(knowledge_path))
        return None

    documents = discover_document_paths(knowledge_path, recursive=True)
    if not documents:
        logger.info("knowledge_sync_no_documents", path=str(knowledge_path))
        return None

    if not settings.rag_sync_knowledge_force and vector_store.count() > 0:
        logger.info(
            "knowledge_sync_skipped_existing_index",
            path=str(knowledge_path),
            vector_count=vector_store.count(),
        )
        return None

    index_path = settings.resolved_rag_default_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    ingest_service = DocumentIngestService(embedding_provider, settings)
    ingest_result = await ingest_service.ingest(
        DocumentIngestOptions(
            input_path=knowledge_path,
            output_path=index_path,
            recursive=True,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        ),
    )

    loader = VectorIndexLoadService(vector_store)
    load_result = loader.load_jsonl(index_path, clear_existing=True)

    logger.info(
        "knowledge_sync_complete",
        knowledge_path=str(knowledge_path),
        documents=ingest_result.files_processed,
        chunks=ingest_result.chunks_written,
        records_loaded=load_result.records_loaded,
        vector_count=vector_store.count(),
    )

    return KnowledgeSyncResult(
        knowledge_path=knowledge_path,
        documents_found=len(documents),
        chunks_written=ingest_result.chunks_written,
        records_loaded=load_result.records_loaded,
        index_path=index_path,
        load_result=load_result,
    )
