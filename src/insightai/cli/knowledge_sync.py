"""CLI: sync Knowledge/ folder into the vector index (startup helper)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.embeddings.factory import create_embedding_provider
from insightai.infrastructure.logging.setup import configure_logging, get_logger
from insightai.infrastructure.rag.knowledge_sync import sync_knowledge_on_startup
from insightai.infrastructure.rag.vector_bootstrap import create_vector_store

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-knowledge-sync",
        description="Ingest Knowledge/ and load embeddings into the configured vector store.",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Override INSIGHTAI_RAG_KNOWLEDGE_PATH (default: Knowledge/).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reload even when the vector store already has chunks.",
    )
    return parser


async def _run(force: bool, knowledge_path: str | None) -> int:
    settings = get_settings()
    configure_logging(settings)

    overrides: dict[str, object] = {
        "rag_enabled": True,
        "rag_sync_knowledge_on_startup": True,
        "rag_sync_knowledge_force": force,
    }
    if knowledge_path:
        overrides["rag_knowledge_path"] = knowledge_path

    settings = settings.model_copy(update=overrides)

    try:
        embedding = create_embedding_provider(settings)
        store = create_vector_store(settings)
    except Exception as exc:
        print(f"knowledge-sync failed: {exc}", file=sys.stderr)
        return 1

    result = await sync_knowledge_on_startup(
        settings=settings,
        embedding_provider=embedding,
        vector_store=store,
    )
    if result is None:
        path = settings.resolved_rag_knowledge_path()
        print(f"No knowledge synced (empty or skipped). Check documents under {path}.")
        return 0

    print(
        f"Synced {result.records_loaded} chunk(s) from {result.documents_found} "
        f"document(s) in {result.knowledge_path}.",
    )
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(_run(args.force, args.path))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
