"""No-op cache used when caching is disabled."""

from __future__ import annotations


class NullCache:
    """Always misses; writes are ignored."""

    async def get(self, key: str) -> str | None:
        del key
        return None

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        del key, value, ttl_seconds

    async def delete(self, key: str) -> bool:
        del key
        return False
