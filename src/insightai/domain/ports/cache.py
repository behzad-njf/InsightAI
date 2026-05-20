"""Port for generic key-value caching (Phase 9.1)."""

from __future__ import annotations

from typing import Protocol


class ICache(Protocol):
    """
    Async string cache for schema context, query results, and similar payloads.

    Values are UTF-8 strings (typically JSON). Callers own serialization.
    """

    async def get(self, key: str) -> str | None:
        """Return a cached value or ``None`` on miss / expiry."""

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store ``value``; use default TTL from settings when ``ttl_seconds`` is ``None``."""

    async def delete(self, key: str) -> bool:
        """Remove ``key``. Returns ``True`` when a entry existed."""
