"""In-memory sliding-window rate limiter."""

from __future__ import annotations

import asyncio
import time

from insightai.domain.models.rate_limit import RateLimitResult


class MemoryRateLimiter:
    """Per-process sliding window limiter (development / single-worker)."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = float(window_seconds)
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        window_start = now - self._window

        async with self._lock:
            timestamps = [t for t in self._hits.get(key, []) if t > window_start]
            if len(timestamps) >= self._limit:
                oldest = timestamps[0]
                retry_after = int(oldest + self._window - now) + 1
                return RateLimitResult(
                    allowed=False,
                    limit=self._limit,
                    remaining=0,
                    retry_after_seconds=max(1, retry_after),
                )

            timestamps.append(now)
            self._hits[key] = timestamps
            remaining = max(0, self._limit - len(timestamps))
            return RateLimitResult(
                allowed=True,
                limit=self._limit,
                remaining=remaining,
                retry_after_seconds=0,
            )
