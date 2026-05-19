"""Build chat session store from settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from insightai.infrastructure.chat.memory_session_store import MemoryChatSessionStore
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.domain.ports.chat_session_store import IChatSessionStore
    from insightai.infrastructure.config.settings import Settings

logger = get_logger(__name__)


class ChatSessionStoreKind(StrEnum):
    MEMORY = "memory"
    REDIS = "redis"


@dataclass(frozen=True)
class ChatSessionComponents:
    """Chat session infrastructure wired at startup."""

    store: IChatSessionStore
    kind: ChatSessionStoreKind


def build_chat_session_store(settings: Settings) -> ChatSessionComponents:
    """Create the configured session store (in-memory by default)."""
    kind = ChatSessionStoreKind(settings.chat_session_store.lower())
    ttl = settings.chat_session_ttl_seconds
    max_messages = settings.chat_session_max_messages

    if kind == ChatSessionStoreKind.REDIS:
        store = _try_build_redis_store(settings, ttl_seconds=ttl, max_messages=max_messages)
        if store is not None:
            logger.info("chat_session_store_configured", kind="redis")
            return ChatSessionComponents(store=store, kind=ChatSessionStoreKind.REDIS)
        logger.warning("chat_session_store_redis_unavailable", fallback="memory")

    memory = MemoryChatSessionStore(
        ttl_seconds=ttl,
        max_messages_per_session=max_messages,
    )
    logger.info("chat_session_store_configured", kind="memory")
    return ChatSessionComponents(store=memory, kind=ChatSessionStoreKind.MEMORY)


def _try_build_redis_store(
    settings: Settings,
    *,
    ttl_seconds: int,
    max_messages: int,
) -> IChatSessionStore | None:
    try:
        from redis.asyncio import from_url
    except ImportError:
        return None

    from insightai.infrastructure.chat.redis_session_store import RedisChatSessionStore

    client = from_url(settings.redis_url, decode_responses=True)
    return RedisChatSessionStore(
        client,
        ttl_seconds=ttl_seconds,
        max_messages_per_session=max_messages,
    )
