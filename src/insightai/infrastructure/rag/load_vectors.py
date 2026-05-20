"""Load JSONL RAG indexes into a vector store (Phase 10.3)."""

from __future__ import annotations

from pathlib import Path

from insightai.domain.models.rag import VectorLoadResult
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.index_store import iter_index_records, load_manifest

logger = get_logger(__name__)


class VectorIndexLoadService:
    """Hydrate a vector store from Phase 10.2 ingest output."""

    def __init__(self, vector_store: IVectorStore) -> None:
        self._store = vector_store

    def load_jsonl(
        self,
        index_path: Path,
        *,
        clear_existing: bool = True,
    ) -> VectorLoadResult:
        path = index_path.resolve()
        if not path.is_file():
            msg = f"JSONL index not found: {path}"
            raise FileNotFoundError(msg)

        manifest = load_manifest(path)
        records = iter_index_records(path)
        if not records:
            msg = f"No records in index: {path}"
            raise ValueError(msg)

        if clear_existing:
            self._store.delete_all()

        self._store.ensure_schema(manifest.dimensions)
        written = self._store.upsert_records(records)

        logger.info(
            "vector_index_loaded",
            path=str(path),
            records=written,
            dimensions=manifest.dimensions,
            cleared=clear_existing,
        )

        table_or_store = type(self._store).__name__
        return VectorLoadResult(
            records_loaded=written,
            dimensions=manifest.dimensions,
            table_or_store=table_or_store,
            cleared_existing=clear_existing,
        )
