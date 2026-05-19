"""Port for chat session persistence (Phase 7.3)."""

from __future__ import annotations

from typing import Protocol

from insightai.domain.models.chat_session import ChatMessage, ChatSession


class IChatSessionStore(Protocol):
    """Store chat sessions and message history."""

    async def create_session(self, *, title: str | None = None) -> ChatSession:
        """Create a new empty session."""

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Return session metadata or ``None`` if missing or expired."""

    async def delete_session(self, session_id: str) -> bool:
        """Delete session and messages. Returns ``False`` if not found."""

    async def append_message(self, message: ChatMessage) -> ChatMessage:
        """Append a message; session must exist."""

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """List messages oldest-first for a session."""
