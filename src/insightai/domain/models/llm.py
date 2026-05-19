"""LLM domain models — provider-agnostic request/response contracts."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LLMRole(StrEnum):
    """Chat message roles supported across providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMProviderKind(StrEnum):
    """Supported LLM provider identifiers (config: INSIGHTAI_LLM_PROVIDER)."""

    GROQ = "groq"
    OPENAI = "openai"


class AIFrameworkKind(StrEnum):
    """Supported AI framework identifiers (config: INSIGHTAI_AI_FRAMEWORK)."""

    LLAMAINDEX = "llamaindex"
    LANGCHAIN = "langchain"


class LLMMessage(BaseModel):
    """Single chat message."""

    role: LLMRole
    content: str = Field(min_length=1)

    model_config = {"frozen": True}


class TokenUsage(BaseModel):
    """Token consumption for a completion (nullable when provider omits usage)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    model_config = {"frozen": True}

    @property
    def has_usage(self) -> bool:
        return any(
            value is not None
            for value in (self.prompt_tokens, self.completion_tokens, self.total_tokens)
        )


class LLMRequest(BaseModel):
    """Provider-agnostic completion request."""

    messages: list[LLMMessage] = Field(min_length=1)
    model: str | None = Field(
        default=None,
        description="Override default model from settings when set.",
    )
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("messages")
    @classmethod
    def validate_messages_not_empty(cls, messages: list[LLMMessage]) -> list[LLMMessage]:
        if not messages:
            msg = "At least one message is required."
            raise ValueError(msg)
        return messages


class LLMResponse(BaseModel):
    """Unified LLM completion response."""

    content: str
    model: str
    provider: LLMProviderKind
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str | None = None
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Optional provider payload for debugging (omit in production logs).",
    )

    model_config = {"frozen": True}


class LLMStreamChunk(BaseModel):
    """
    One piece of a streaming completion.

    Providers yield many chunks with ``text`` deltas; the final chunk may include
    ``finish_reason`` and ``usage`` (with ``text`` empty or omitted).
    """

    text: str | None = Field(
        default=None,
        description="Incremental completion text; omit on metadata-only chunks.",
    )
    finish_reason: str | None = None
    usage: TokenUsage | None = None

    model_config = {"frozen": True}

    @property
    def has_text(self) -> bool:
        return bool(self.text)

    @property
    def is_terminal(self) -> bool:
        return self.finish_reason is not None or (
            self.usage is not None and self.usage.has_usage
        )


def join_stream_text(chunks: Iterable[LLMStreamChunk]) -> str:
    """Concatenate text deltas from a stream into one string."""
    return "".join(chunk.text for chunk in chunks if chunk.text)
