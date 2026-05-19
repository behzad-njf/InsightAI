"""Redis sliding-window rate limiter."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from insightai.domain.models.rate_limit import RateLimitResult

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _redis_key(identifier: str) -> str:
    return f"insightai:ratelimit:{identifier}"


class RedisRateLimiter:
    """Distributed sliding window using a Redis sorted set."""

    def __init__(
        self,
        client: Redis,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        self._client = client
        self._limit = limit
        self._window = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        now = time.time()
        window_start = now - self._window
        redis_key = _redis_key(key)
        member = f"{now}"

        async with self._client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, self._window + 1)
            results = await pipe.execute()

        count = int(results[2])
        if count > self._limit:
            oldest = await self._client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                oldest_ts = float(oldest[0][1])
                retry_after = max(1, int(oldest_ts + self._window - now) + 1)
            await self._client.zrem(redis_key, member)
            return RateLimitResult(
                allowed=False,
                limit=self._limit,
                remaining=0,
                retry_after_seconds=retry_after,
            )

        remaining = max(0, self._limit - count)
        return RateLimitResult(
            allowed=True,
            limit=self._limit,
            remaining=remaining,
            retry_after_seconds=0,
        )
