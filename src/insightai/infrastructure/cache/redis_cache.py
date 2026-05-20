"""Redis-backed string cache (optional ``redis`` package)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.infrastructure.cache.keys import qualify_key

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisCache:
    """Distributed cache using ``SET`` / ``GET`` with TTL."""

    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str,
        default_ttl_seconds: int,
    ) -> None:
        self._client = client
        self._prefix = key_prefix
        self._default_ttl = default_ttl_seconds

    async def get(self, key: str) -> str | None:
        raw = await self._client.get(qualify_key(self._prefix, key))
        return raw if isinstance(raw, str) else None

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        qualified = qualify_key(self._prefix, key)
        ttl = self._default_ttl if ttl_seconds is None else ttl_seconds
        if ttl > 0:
            await self._client.set(qualified, value, ex=ttl)
        else:
            await self._client.set(qualified, value)

    async def delete(self, key: str) -> bool:
        deleted = await self._client.delete(qualify_key(self._prefix, key))
        return int(deleted) > 0
