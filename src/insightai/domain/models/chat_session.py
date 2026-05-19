"""Chat session and message models (Phase 7.3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ChatMessageRole(StrEnum):
    """Conversation role for stored messages."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(BaseModel):
    """A client conversation thread."""

    id: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    message_count: int = Field(default=0, ge=0)

    model_config = {"frozen": True}


class ChatMessage(BaseModel):
    """Single turn in a chat session."""

    id: str
    session_id: str
    role: ChatMessageRole
    content: str = Field(min_length=1)
    created_at: datetime
    request_id: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    sql: str | None = None

    model_config = {"frozen": True}
