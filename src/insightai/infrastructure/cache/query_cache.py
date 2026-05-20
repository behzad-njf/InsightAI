"""Query result cache keys and serialization (Phase 9.3)."""

from __future__ import annotations

import hashlib

from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions  # noqa: TC001
from insightai.domain.models.query_execution import RunQueryResult
from insightai.domain.ports.cache import ICache  # noqa: TC001
from insightai.infrastructure.cache.keys import build_cache_key


def query_result_cache_key(
    sql: str,
    options: QueryExecutionOptions,
    database_kind: DatabaseKind,
    *,
    cache_scope: str | None = None,
) -> str:
    """
    Stable cache key for a read-only query result.

    Uses normalized SQL text, execution limits, dialect, and optional user scope.
    """
    normalized_sql = " ".join(sql.strip().split())
    fingerprint = (
        f"{normalized_sql}|{options.max_rows}|{options.timeout_seconds}|"
        f"{options.enforce_readonly}|{database_kind.value}|{cache_scope or ''}"
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()
    return build_cache_key("query", "result", digest)


async def get_cached_run_query_result(
    cache: ICache,
    key: str,
) -> RunQueryResult | None:
    raw = await cache.get(key)
    if raw is None:
        return None
    return RunQueryResult.model_validate_json(raw)


async def set_cached_run_query_result(
    cache: ICache,
    key: str,
    result: RunQueryResult,
    *,
    ttl_seconds: int,
) -> None:
    await cache.set(key, result.model_dump_json(), ttl_seconds=ttl_seconds)
