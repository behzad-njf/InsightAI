"""CLI: load JSONL RAG index into pgvector (Phase 10.3)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.logging.setup import configure_logging, get_logger
from insightai.infrastructure.rag.load_vectors import VectorIndexLoadService
from insightai.infrastructure.rag.vector_bootstrap import create_vector_store

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-rag-load",
        description="Load insightai-ingest JSONL output into a vector store (pgvector).",
    )
    parser.add_argument(
        "--index",
        "-i",
        type=Path,
        default=None,
        help="Path to chunks.jsonl (default: INSIGHTAI_RAG_DEFAULT_INDEX_PATH).",
    )
    parser.add_argument(
        "--backend",
        choices=("pgvector", "memory"),
        default=None,
        help="Vector backend override (default from settings).",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Append/upsert without truncating existing rows.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings)

    index_path = args.index or settings.rag_default_index_path

    try:
        store = create_vector_store(settings, backend=args.backend)
        service = VectorIndexLoadService(store)
        result = service.load_jsonl(index_path, clear_existing=not args.no_clear)
    except Exception as exc:
        print(f"rag-load failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    logger.info(
        "rag_load_cli_complete",
        records=result.records_loaded,
        store=result.table_or_store,
    )
    print(
        f"Loaded {result.records_loaded} chunk(s) into {result.table_or_store} "
        f"(dimensions={result.dimensions}, cleared={result.cleared_existing}).",
    )


if __name__ == "__main__":
    main()
