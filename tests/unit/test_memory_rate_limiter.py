"""Unit tests for in-memory sliding-window rate limiter."""

from __future__ import annotations

import pytest

from insightai.infrastructure.ratelimit.memory_limiter import MemoryRateLimiter


@pytest.mark.asyncio
async def test_allows_up_to_limit() -> None:
    limiter = MemoryRateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        result = await limiter.check("client-a")
        assert result.allowed is True
    blocked = await limiter.check("client-a")
    assert blocked.allowed is False
    assert blocked.retry_after_seconds >= 1
    assert blocked.remaining == 0


@pytest.mark.asyncio
async def test_separate_keys() -> None:
    limiter = MemoryRateLimiter(limit=1, window_seconds=60)
    assert (await limiter.check("a")).allowed is True
    assert (await limiter.check("b")).allowed is True
    assert (await limiter.check("a")).allowed is False
