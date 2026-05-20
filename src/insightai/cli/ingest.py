"""CLI: ingest documents into a local RAG index (Phase 10.2)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from insightai.domain.models.rag import DocumentIngestOptions
from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.embeddings.factory import create_embedding_provider
from insightai.infrastructure.logging.setup import configure_logging, get_logger
from insightai.infrastructure.rag.ingest import DocumentIngestService

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-ingest",
        description="Chunk documents, embed them, and write a JSONL RAG index.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="File or directory with .md, .txt, or .pdf sources.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/rag_index/chunks.jsonl"),
        help="Output JSONL path (manifest.json written alongside).",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When input is a directory, scan subdirectories (default: true).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Max characters per chunk (default from settings / 800).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Character overlap between chunks (default from settings / 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk only; do not call embeddings or write files.",
    )
    return parser


async def run_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings)

    chunk_size = args.chunk_size if args.chunk_size is not None else settings.rag_chunk_size
    chunk_overlap = (
        args.chunk_overlap if args.chunk_overlap is not None else settings.rag_chunk_overlap
    )

    options = DocumentIngestOptions(
        input_path=args.input,
        output_path=args.output,
        recursive=args.recursive,
        dry_run=args.dry_run,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    provider = create_embedding_provider(settings)
    service = DocumentIngestService(provider, settings)
    result = await service.ingest(options)

    logger.info(
        "ingest_cli_complete",
        files=result.files_processed,
        chunks=result.manifest.chunk_count,
        written=result.chunks_written,
        skipped=len(result.files_skipped),
        dry_run=args.dry_run,
    )

    print(
        f"Ingested {result.files_processed} file(s) → "
        f"{result.manifest.chunk_count} chunk(s)"
        + (" (dry-run, not written)" if args.dry_run else f" → {result.manifest.output_path}"),
    )
    if result.files_skipped:
        print(f"Skipped {len(result.files_skipped)} file(s).", file=sys.stderr)

    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run_ingest(args)))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
