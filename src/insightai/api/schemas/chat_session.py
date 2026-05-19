"""API schemas for chat session CRUD (Phase 7.3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from insightai.domain.models.chat_session import ChatMessage, ChatMessageRole, ChatSession


class CreateChatSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class ChatSessionResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    message_count: int

    @classmethod
    def from_domain(cls, session: ChatSession) -> ChatSessionResponse:
        return cls(
            id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            title=session.title,
            message_count=session.message_count,
        )


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: ChatMessageRole
    content: str
    created_at: datetime
    request_id: str | None = None
    row_count: int | None = None
    sql: str | None = None

    @classmethod
    def from_domain(cls, message: ChatMessage) -> ChatMessageResponse:
        return cls(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            request_id=message.request_id,
            row_count=message.row_count,
            sql=message.sql,
        )


class ChatMessageListResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageResponse]
    total: int
