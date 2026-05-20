"""Unit tests for Phase 9.1 cache port and adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from insightai.infrastructure.cache.bootstrap import CacheStoreKind, build_cache
from insightai.infrastructure.cache.keys import build_cache_key, qualify_key
from insightai.infrastructure.cache.memory_cache import MemoryCache
from insightai.infrastructure.cache.null_cache import NullCache
from insightai.infrastructure.cache.redis_cache import RedisCache
from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_null_cache_always_misses() -> None:
    cache = NullCache()
    await cache.set("k", "v")
    assert await cache.get("k") is None
    assert await cache.delete("k") is False


@pytest.mark.asyncio
async def test_memory_cache_round_trip() -> None:
    cache = MemoryCache(key_prefix="insightai:cache:", default_ttl_seconds=60)
    await cache.set("schema:ctx:abc", '{"tables":[]}')
    assert await cache.get("schema:ctx:abc") == '{"tables":[]}'
    assert await cache.delete("schema:ctx:abc") is True
    assert await cache.get("schema:ctx:abc") is None


@pytest.mark.asyncio
async def test_memory_cache_expires_entries() -> None:
    cache = MemoryCache(key_prefix="p:", default_ttl_seconds=1)

    with patch("insightai.infrastructure.cache.memory_cache.time.monotonic") as mono:
        mono.return_value = 0.0
        await cache.set("ttl-key", "gone", ttl_seconds=1)
        assert await cache.get("ttl-key") == "gone"
        mono.return_value = 2.0
        assert await cache.get("ttl-key") is None


@pytest.mark.asyncio
async def test_redis_cache_uses_prefixed_keys() -> None:
    client = AsyncMock()
    client.get.return_value = "payload"
    client.delete.return_value = 1

    cache = RedisCache(client, key_prefix="insightai:cache:", default_ttl_seconds=30)
    assert await cache.get("query:1") == "payload"
    client.get.assert_awaited_once_with("insightai:cache:query:1")

    await cache.set("query:2", "data", ttl_seconds=10)
    client.set.assert_awaited_once_with("insightai:cache:query:2", "data", ex=10)

    assert await cache.delete("query:1") is True
    client.delete.assert_awaited_with("insightai:cache:query:1")


def test_qualify_key_and_build_cache_key() -> None:
    prefix = "insightai:cache:"
    assert qualify_key(prefix, "schema:x") == "insightai:cache:schema:x"
    assert qualify_key(prefix, "insightai:cache:already") == "insightai:cache:already"
    assert build_cache_key("schema", "context", "abc123") == "schema:context:abc123"


def test_build_cache_disabled_returns_null() -> None:
    settings = make_settings(cache_enabled=False)
    components = build_cache(settings)
    assert components.enabled is False
    assert components.kind == CacheStoreKind.DISABLED


def test_build_cache_memory_when_enabled() -> None:
    settings = make_settings(cache_enabled=True, cache_store="memory")
    components = build_cache(settings)
    assert components.enabled is True
    assert components.kind == CacheStoreKind.MEMORY
    assert components.redis_client is None


def test_build_cache_redis_fallback_to_memory_without_package() -> None:
    settings = make_settings(cache_enabled=True, cache_store="redis")
    with patch(
        "insightai.infrastructure.cache.bootstrap.create_redis_client",
        return_value=None,
    ):
        components = build_cache(settings)
    assert components.enabled is True
    assert components.kind == CacheStoreKind.MEMORY


def test_build_cache_redis_when_client_available() -> None:
    settings = make_settings(cache_enabled=True, cache_store="redis")
    client = MagicMock()
    with patch(
        "insightai.infrastructure.cache.bootstrap.create_redis_client",
        return_value=client,
    ):
        components = build_cache(settings)
    assert components.enabled is True
    assert components.kind == CacheStoreKind.REDIS
    assert components.redis_client is client


@pytest.mark.asyncio
async def test_lifespan_closes_redis_client() -> None:
    from insightai.domain.exceptions import ConfigurationError
    from insightai.main import create_app

    settings = make_settings(
        groq_api_key="gsk-cache-test",
        cache_enabled=True,
        cache_store="redis",
    )
    mock_client = AsyncMock()
    mock_components = MagicMock()
    mock_components.redis_client = mock_client
    mock_components.enabled = True
    mock_components.kind = CacheStoreKind.REDIS

    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch("insightai.main.build_cache", return_value=mock_components),
        patch("insightai.main.build_ai_components"),
        patch(
            "insightai.main.build_database_components",
            side_effect=ConfigurationError("skip"),
        ),
        patch("insightai.main.build_chat_session_store"),
        patch("insightai.main.build_rate_limiter"),
        patch("insightai.main.build_audit_logger"),
        patch("insightai.main.configure_tracing", return_value=False),
        patch("insightai.main.configure_metrics", return_value=False),
    ):
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as _client:
            pass

    mock_client.aclose.assert_awaited_once()
