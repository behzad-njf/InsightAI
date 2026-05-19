"""Redis-backed chat session store (optional ``redis`` package)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from insightai.domain.exceptions import ChatSessionNotFoundError
from insightai.domain.models.chat_session import ChatMessage, ChatSession

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _session_key(session_id: str) -> str:
    return f"insightai:chat:session:{session_id}"


def _messages_key(session_id: str) -> str:
    return f"insightai:chat:messages:{session_id}"


class RedisChatSessionStore:
    """Persist sessions and message lists in Redis with TTL."""

    def __init__(
        self,
        client: Redis,
        *,
        ttl_seconds: int,
        max_messages_per_session: int,
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._max_messages = max_messages_per_session

    async def create_session(self, *, title: str | None = None) -> ChatSession:
        now = datetime.now(UTC)
        session = ChatSession(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            title=title.strip() if title else None,
            message_count=0,
        )
        payload = session.model_dump(mode="json")
        key = _session_key(session.id)
        await self._client.set(key, json.dumps(payload), ex=self._ttl)
        await self._client.delete(_messages_key(session.id))
        return session

    async def get_session(self, session_id: str) -> ChatSession | None:
        raw = await self._client.get(_session_key(session_id))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(raw)
        return ChatSession.model_validate(data)

    async def delete_session(self, session_id: str) -> bool:
        deleted = await self._client.delete(
            _session_key(session_id),
            _messages_key(session_id),
        )
        return deleted > 0

    async def append_message(self, message: ChatMessage) -> ChatMessage:
        session_key = _session_key(message.session_id)
        if not await self._client.exists(session_key):
            raise ChatSessionNotFoundError(message.session_id)

        msg_key = _messages_key(message.session_id)
        payload = message.model_dump(mode="json")
        async with self._client.pipeline(transaction=True) as pipe:
            await pipe.rpush(msg_key, json.dumps(payload))
            await pipe.ltrim(msg_key, -self._max_messages, -1)
            await pipe.expire(msg_key, self._ttl)
            await pipe.execute()

        session = await self.get_session(message.session_id)
        if session is None:
            raise ChatSessionNotFoundError(message.session_id)
        count = await self._client.llen(msg_key)
        updated = session.model_copy(
            update={
                "updated_at": message.created_at,
                "message_count": count,
            },
        )
        await self._client.set(
            session_key,
            json.dumps(updated.model_dump(mode="json")),
            ex=self._ttl,
        )
        return message

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        if not await self._client.exists(_session_key(session_id)):
            return []
        raw_items = await self._client.lrange(
            _messages_key(session_id),
            offset,
            offset + limit - 1,
        )
        return [ChatMessage.model_validate(json.loads(raw)) for raw in raw_items]
