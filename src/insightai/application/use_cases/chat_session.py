"""Chat session lifecycle and message history (Phase 7.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from insightai.domain.exceptions import (
    ChatSessionMessageLimitError,
    ChatSessionNotFoundError,
)
from insightai.domain.models.chat_session import ChatMessage, ChatMessageRole, ChatSession
from insightai.infrastructure.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from insightai.domain.models.ask import AskResult
    from insightai.domain.ports.chat_session_store import IChatSessionStore


class ChatSessionUseCase:
    """Create sessions, fetch history, and record chat turns."""

    def __init__(
        self,
        store: IChatSessionStore,
        settings: Settings | None = None,
    ) -> None:
        self._store = store
        self._settings = settings or get_settings()

    async def create(self, *, title: str | None = None) -> ChatSession:
        return await self._store.create_session(title=title)

    async def get(self, session_id: str) -> ChatSession:
        return await self.require_session(session_id)

    async def delete(self, session_id: str) -> bool:
        return await self._store.delete_session(session_id)

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ChatMessage]:
        await self.require_session(session_id)
        resolved_limit = (
            limit if limit is not None else self._settings.chat_session_list_default_limit
        )
        return await self._store.list_messages(
            session_id,
            limit=resolved_limit,
            offset=offset,
        )

    async def require_session(self, session_id: str) -> ChatSession:
        session = await self._store.get_session(session_id)
        if session is None:
            raise ChatSessionNotFoundError(session_id)
        return session

    async def record_exchange(
        self,
        session_id: str,
        *,
        question: str,
        result: AskResult,
        request_id: str | None = None,
        store_sql: bool = False,
    ) -> None:
        """Append user question and assistant answer to session history."""
        session = await self.require_session(session_id)
        max_messages = self._settings.chat_session_max_messages
        if session.message_count + 2 > max_messages:
            raise ChatSessionMessageLimitError(session_id, limit=max_messages)

        now = datetime.now(UTC)
        await self._store.append_message(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=ChatMessageRole.USER,
                content=question,
                created_at=now,
                request_id=request_id,
            ),
        )
        await self._store.append_message(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=ChatMessageRole.ASSISTANT,
                content=result.answer.answer.answer,
                created_at=datetime.now(UTC),
                request_id=request_id,
                row_count=(
                    result.execution.query_result.row_count
                    if result.execution is not None
                    else result.answer.answer.row_count
                ),
                sql=(
                    result.execution.sql
                    if store_sql and result.execution is not None
                    else None
                ),
            ),
        )
