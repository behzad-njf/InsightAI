"""Build rate limiter from settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from insightai.domain.ports.rate_limiter import IRateLimiter
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.ratelimit.memory_limiter import MemoryRateLimiter

logger = get_logger(__name__)


class RateLimitStoreKind(StrEnum):
    MEMORY = "memory"
    REDIS = "redis"


@dataclass(frozen=True)
class RateLimitComponents:
    """Rate limiter wired at application startup."""

    limiter: IRateLimiter | None
    kind: RateLimitStoreKind
    enabled: bool


def build_rate_limiter(settings: Settings) -> RateLimitComponents:
    """Create limiter when enabled; otherwise return a no-op configuration."""
    if not settings.rate_limit_enabled:
        logger.info("rate_limit_disabled")
        return RateLimitComponents(
            limiter=None,
            kind=RateLimitStoreKind.MEMORY,
            enabled=False,
        )

    limit = settings.rate_limit_requests
    window = settings.rate_limit_window_seconds
    kind = RateLimitStoreKind(settings.rate_limit_store.lower())

    if kind == RateLimitStoreKind.REDIS:
        redis_limiter = _try_build_redis(settings, limit=limit, window_seconds=window)
        if redis_limiter is not None:
            logger.info(
                "rate_limit_configured",
                kind="redis",
                limit=limit,
                window_seconds=window,
            )
            return RateLimitComponents(
                limiter=redis_limiter,
                kind=RateLimitStoreKind.REDIS,
                enabled=True,
            )
        logger.warning("rate_limit_redis_unavailable", fallback="memory")

    memory = MemoryRateLimiter(limit=limit, window_seconds=window)
    logger.info(
        "rate_limit_configured",
        kind="memory",
        limit=limit,
        window_seconds=window,
    )
    return RateLimitComponents(
        limiter=memory,
        kind=RateLimitStoreKind.MEMORY,
        enabled=True,
    )


def _try_build_redis(
    settings: Settings,
    *,
    limit: int,
    window_seconds: int,
) -> IRateLimiter | None:
    try:
        from redis.asyncio import from_url
    except ImportError:
        return None

    from insightai.infrastructure.ratelimit.redis_limiter import RedisRateLimiter

    client = from_url(settings.redis_url, decode_responses=True)
    return RedisRateLimiter(client, limit=limit, window_seconds=window_seconds)
