"""In-memory chat session store for development and tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from insightai.domain.exceptions import ChatSessionNotFoundError
from insightai.domain.models.chat_session import ChatMessage, ChatSession


class MemoryChatSessionStore:
    """Thread-safe in-process session store with TTL expiry."""

    def __init__(self, *, ttl_seconds: int, max_messages_per_session: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_messages = max_messages_per_session
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatMessage]] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, *, title: str | None = None) -> ChatSession:
        now = datetime.now(UTC)
        session = ChatSession(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            title=title.strip() if title else None,
            message_count=0,
        )
        async with self._lock:
            self._sessions[session.id] = session
            self._messages[session.id] = []
        return session

    async def get_session(self, session_id: str) -> ChatSession | None:
        async with self._lock:
            self._purge_expired_locked()
            return self._sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            existed = session_id in self._sessions
            self._sessions.pop(session_id, None)
            self._messages.pop(session_id, None)
            return existed

    async def append_message(self, message: ChatMessage) -> ChatMessage:
        async with self._lock:
            self._purge_expired_locked()
            session = self._sessions.get(message.session_id)
            if session is None:
                raise ChatSessionNotFoundError(message.session_id)
            bucket = self._messages.setdefault(message.session_id, [])
            bucket.append(message)
            updated = session.model_copy(
                update={
                    "updated_at": message.created_at,
                    "message_count": len(bucket),
                },
            )
            self._sessions[message.session_id] = updated
            return message

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        async with self._lock:
            self._purge_expired_locked()
            if session_id not in self._sessions:
                return []
            bucket = self._messages.get(session_id, [])
            end = offset + limit
            return list(bucket[offset:end])

    def _purge_expired_locked(self) -> None:
        cutoff = datetime.now(UTC) - self._ttl
        expired = [
            sid
            for sid, session in self._sessions.items()
            if session.updated_at < cutoff
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._messages.pop(sid, None)
