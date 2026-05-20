"""In-process string cache with optional TTL (Phase 9.1)."""

from __future__ import annotations

import asyncio
import time

from insightai.infrastructure.cache.keys import qualify_key


class MemoryCache:
    """Per-process cache for development and single-worker deployments."""

    def __init__(
        self,
        *,
        key_prefix: str,
        default_ttl_seconds: int,
    ) -> None:
        self._prefix = key_prefix
        self._default_ttl = default_ttl_seconds
        self._entries: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        qualified = qualify_key(self._prefix, key)
        async with self._lock:
            entry = self._entries.get(qualified)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.monotonic() >= expires_at:
                del self._entries[qualified]
                return None
            return value

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        qualified = qualify_key(self._prefix, key)
        ttl = self._default_ttl if ttl_seconds is None else ttl_seconds
        expires_at = time.monotonic() + float(ttl) if ttl > 0 else None
        async with self._lock:
            self._entries[qualified] = (value, expires_at)

    async def delete(self, key: str) -> bool:
        qualified = qualify_key(self._prefix, key)
        async with self._lock:
            return self._entries.pop(qualified, None) is not None
