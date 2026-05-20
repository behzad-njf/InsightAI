"""Build cache adapter from settings (Phase 9.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from insightai.infrastructure.cache.memory_cache import MemoryCache
from insightai.infrastructure.cache.null_cache import NullCache
from insightai.infrastructure.cache.redis_client import create_redis_client
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.domain.ports.cache import ICache
    from insightai.infrastructure.config.settings import Settings

logger = get_logger(__name__)


class CacheStoreKind(StrEnum):
    MEMORY = "memory"
    REDIS = "redis"
    DISABLED = "disabled"


@dataclass(frozen=True)
class CacheComponents:
    """Cache infrastructure wired at application startup."""

    cache: ICache
    kind: CacheStoreKind
    enabled: bool
    redis_client: Any | None = None


def build_cache(settings: Settings) -> CacheComponents:
    """Create the configured cache (disabled no-op by default)."""
    if not settings.cache_enabled:
        logger.info("cache_disabled")
        return CacheComponents(
            cache=NullCache(),
            kind=CacheStoreKind.DISABLED,
            enabled=False,
        )

    prefix = settings.cache_key_prefix
    default_ttl = settings.cache_default_ttl_seconds
    kind = CacheStoreKind(settings.cache_store.lower())

    if kind == CacheStoreKind.REDIS:
        redis_bundle = _try_build_redis_cache(
            settings,
            key_prefix=prefix,
            default_ttl_seconds=default_ttl,
        )
        if redis_bundle is not None:
            cache, client = redis_bundle
            logger.info(
                "cache_configured",
                kind="redis",
                default_ttl_seconds=default_ttl,
            )
            return CacheComponents(
                cache=cache,
                kind=CacheStoreKind.REDIS,
                enabled=True,
                redis_client=client,
            )
        logger.warning("cache_redis_unavailable", fallback="memory")

    memory = MemoryCache(key_prefix=prefix, default_ttl_seconds=default_ttl)
    logger.info(
        "cache_configured",
        kind="memory",
        default_ttl_seconds=default_ttl,
    )
    return CacheComponents(
        cache=memory,
        kind=CacheStoreKind.MEMORY,
        enabled=True,
    )


def _try_build_redis_cache(
    settings: Settings,
    *,
    key_prefix: str,
    default_ttl_seconds: int,
) -> tuple[ICache, Any] | None:
    client = create_redis_client(settings.redis_url)
    if client is None:
        return None

    from insightai.infrastructure.cache.redis_cache import RedisCache

    return (
        RedisCache(
            client,
            key_prefix=key_prefix,
            default_ttl_seconds=default_ttl_seconds,
        ),
        client,
    )
