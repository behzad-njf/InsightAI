"""LLM API request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from insightai.domain.models.llm import LLMMessage, LLMRequest, LLMRole


class LLMMessageSchema(BaseModel):
    role: LLMRole
    content: str = Field(min_length=1)

    def to_domain(self) -> LLMMessage:
        return LLMMessage(role=self.role, content=self.content)


class LLMCompleteRequest(BaseModel):
    """Smoke-test completion request (Phase 7)."""

    messages: list[LLMMessageSchema] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False

    def to_domain(self, *, default_temperature: float) -> LLMRequest:
        return LLMRequest(
            messages=[message.to_domain() for message in self.messages],
            model=self.model,
            temperature=self.temperature if self.temperature is not None else default_temperature,
            max_tokens=self.max_tokens,
            stream=self.stream,
        )


class TokenUsageSchema(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMCompleteResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: TokenUsageSchema
    finish_reason: str | None = None
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Included only when INSIGHTAI_DEBUG=true",
    )


class LLMStreamTokenSchema(BaseModel):
    """SSE ``token`` event for ``POST /api/v1/ai/complete/stream``."""

    text: str


class LLMStreamErrorSchema(BaseModel):
    """SSE ``error`` event for LLM stream."""

    error_message: str
    error_code: str | None = None
