"""Caching adapters (Phase 9)."""

from insightai.infrastructure.cache.bootstrap import (
    CacheComponents,
    CacheStoreKind,
    build_cache,
)
from insightai.infrastructure.cache.keys import build_cache_key, qualify_key
from insightai.infrastructure.cache.query_cache import (
    get_cached_run_query_result,
    query_result_cache_key,
    set_cached_run_query_result,
)

__all__ = [
    "CacheComponents",
    "CacheStoreKind",
    "build_cache",
    "build_cache_key",
    "get_cached_run_query_result",
    "qualify_key",
    "query_result_cache_key",
    "set_cached_run_query_result",
]
