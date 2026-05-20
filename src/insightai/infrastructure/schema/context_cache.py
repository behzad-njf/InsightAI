"""Schema context cache keys and serialization (Phase 9.2)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.domain.ports.cache import ICache
from insightai.infrastructure.cache.keys import build_cache_key


def schema_context_cache_key(
    request: SchemaContextRequest,
    schema_path: Path,
    *,
    cache_scope: str | None = None,
) -> str:
    """
    Stable cache key for a schema context result.

    Includes question, ``max_tables``, schema file identity (path + mtime), and
    optional ``cache_scope`` (e.g. auth subject when user-scoped caching is enabled).
    """
    normalized_question = " ".join(request.question.strip().lower().split())
    try:
        mtime = schema_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    fingerprint = (
        f"{normalized_question}|{request.max_tables}|"
        f"{schema_path.resolve()}|{mtime}|{cache_scope or ''}"
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()
    return build_cache_key("schema", "context", digest)


async def get_cached_schema_context(
    cache: ICache,
    key: str,
) -> SchemaContextResult | None:
    raw = await cache.get(key)
    if raw is None:
        return None
    return SchemaContextResult.model_validate_json(raw)


async def set_cached_schema_context(
    cache: ICache,
    key: str,
    result: SchemaContextResult,
    *,
    ttl_seconds: int,
) -> None:
    await cache.set(key, result.model_dump_json(), ttl_seconds=ttl_seconds)
