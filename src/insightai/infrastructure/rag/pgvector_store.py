"""PostgreSQL pgvector vector store (Phase 10.3)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from insightai.domain.exceptions import VectorStoreError
from insightai.domain.models.rag import (
    IngestedChunkRecord,
    VectorSearchRequest,
    VectorSearchResult,
)
from insightai.domain.ports.vector_store import IVectorStore
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.rag.vector_utils import validate_sql_identifier, vector_literal

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.infrastructure.config.settings import Settings

logger = get_logger(__name__)


class PgVectorStore(IVectorStore):
    """Store and search chunk embeddings using the pgvector extension."""

    def __init__(self, engine: Engine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings
        self._table = validate_sql_identifier(settings.rag_vector_table, label="table name")
        self._index = validate_sql_identifier(
            settings.rag_vector_index_name,
            label="index name",
        )
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def ensure_schema(self, dimensions: int) -> None:
        table = self._table
        index = self._index
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        source_path TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        title TEXT,
                        section TEXT,
                        embedding vector({dimensions}) NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """,
                ),
            )
            conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS {index}
                    ON {table}
                    USING hnsw (embedding vector_cosine_ops)
                    """,
                ),
            )
        self._dimensions = dimensions
        logger.info("pgvector_schema_ready", table=table, dimensions=dimensions)

    def upsert_records(self, records: list[IngestedChunkRecord]) -> int:
        if not records:
            return 0

        dimensions = len(records[0].embedding)
        if self._dimensions is None:
            self.ensure_schema(dimensions)
        elif dimensions != self._dimensions:
            msg = (
                f"Embedding dimension {dimensions} does not match "
                f"store dimension {self._dimensions}."
            )
            raise VectorStoreError(msg)

        table = self._table
        sql = text(
            f"""
            INSERT INTO {table} (
                id, source_path, chunk_index, text, title, section, embedding, metadata
            )
            VALUES (
                :id, :source_path, :chunk_index, :text, :title, :section,
                CAST(:embedding AS vector), CAST(:metadata AS jsonb)
            )
            ON CONFLICT (id) DO UPDATE SET
                source_path = EXCLUDED.source_path,
                chunk_index = EXCLUDED.chunk_index,
                text = EXCLUDED.text,
                title = EXCLUDED.title,
                section = EXCLUDED.section,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata
            """,
        )

        params = [_record_params(record) for record in records]
        batch_size = self._settings.rag_vector_upsert_batch_size
        with self._engine.begin() as conn:
            for batch_start in range(0, len(params), batch_size):
                batch = params[batch_start : batch_start + batch_size]
                conn.execute(sql, batch)

        return len(records)

    def search(self, request: VectorSearchRequest) -> list[VectorSearchResult]:
        if self._dimensions is None:
            return []
        if len(request.query_embedding) != self._dimensions:
            msg = (
                f"Query embedding dimension {len(request.query_embedding)} "
                f"!= store dimension {self._dimensions}."
            )
            raise VectorStoreError(msg)

        table = self._table
        query_vec = vector_literal(request.query_embedding)
        sql = text(
            f"""
            SELECT
                id,
                source_path,
                chunk_index,
                text,
                title,
                section,
                metadata,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM {table}
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
            """,
        )

        with self._engine.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "query_embedding": query_vec,
                    "top_k": request.top_k,
                },
            ).mappings().all()

        results: list[VectorSearchResult] = []
        for row in rows:
            score = float(row["score"])
            if request.min_score is not None and score < request.min_score:
                continue
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if not isinstance(metadata, dict):
                metadata = {}
            results.append(
                VectorSearchResult(
                    id=str(row["id"]),
                    source_path=str(row["source_path"]),
                    chunk_index=int(row["chunk_index"]),
                    text=str(row["text"]),
                    score=score,
                    title=row["title"],
                    section=row["section"],
                    metadata=metadata,
                ),
            )
        return results

    def delete_all(self) -> None:
        table = self._table
        with self._engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table}"))
        logger.info("pgvector_table_truncated", table=table)

    def count(self) -> int:
        table = self._table
        with self._engine.connect() as conn:
            value = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        return int(value or 0)


def _record_params(record: IngestedChunkRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "source_path": record.source_path,
        "chunk_index": record.chunk_index,
        "text": record.text,
        "title": record.title,
        "section": record.section,
        "embedding": vector_literal(record.embedding),
        "metadata": json.dumps(record.metadata),
    }
