"""Rate limit dependency for protected API routes (Phase 7.5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from insightai.api.deps import get_settings
from insightai.domain.exceptions import RateLimitExceededError
from insightai.domain.ports.rate_limiter import IRateLimiter
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.ratelimit.keys import resolve_rate_limit_key


def get_rate_limiter(request: Request) -> IRateLimiter | None:
    components = request.app.state.rate_limit
    return components.limiter if components.enabled else None


async def enforce_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """
    Apply sliding-window rate limits after authentication.

    Runs on the protected ``/api/v1`` router only.
    """
    limiter = get_rate_limiter(request)
    if limiter is None:
        return

    key = resolve_rate_limit_key(request, settings)
    result = await limiter.check(key)
    if not result.allowed:
        raise RateLimitExceededError(
            f"Rate limit exceeded: {result.limit} requests per "
            f"{settings.rate_limit_window_seconds}s.",
            retry_after_seconds=result.retry_after_seconds,
            limit=result.limit,
        )
