"""Shared Redis client factory (Phase 9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis | None:
    """
    Build an asyncio Redis client from ``INSIGHTAI_REDIS_URL``.

    Returns ``None`` when the optional ``redis`` package is not installed.
    """
    try:
        from redis.asyncio import from_url
    except ImportError:
        return None

    return from_url(redis_url, decode_responses=True)
