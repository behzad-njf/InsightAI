"""Port for HTTP rate limiting (Phase 7.5)."""

from __future__ import annotations

from typing import Protocol

from insightai.domain.models.rate_limit import RateLimitResult


class IRateLimiter(Protocol):
    """Sliding-window request rate limiter."""

    async def check(self, key: str) -> RateLimitResult:
        """Record one request for ``key`` or reject when over limit."""
