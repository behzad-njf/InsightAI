"""Embedding domain models (Phase 10.1)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class EmbeddingProviderKind(StrEnum):
    """Supported embedding backends (``INSIGHTAI_EMBEDDING_PROVIDER``)."""

    OPENAI = "openai"
    LOCAL = "local"


class EmbeddingUsage(BaseModel):
    """Token usage when the provider reports it (OpenAI embeddings API)."""

    prompt_tokens: int | None = None
    total_tokens: int | None = None

    model_config = {"frozen": True}

    @property
    def has_usage(self) -> bool:
        return self.prompt_tokens is not None or self.total_tokens is not None


class EmbeddingRequest(BaseModel):
    """Batch embedding request — one vector per input string (order preserved)."""

    texts: list[str] = Field(min_length=1)
    model: str | None = Field(
        default=None,
        description="Optional model override; uses provider default when None.",
    )

    model_config = {"frozen": True}

    @field_validator("texts")
    @classmethod
    def texts_must_not_be_blank(cls, values: list[str]) -> list[str]:
        cleaned = [text.strip() for text in values]
        if not cleaned or any(not text for text in cleaned):
            msg = "Embedding texts must be non-empty strings."
            raise ValueError(msg)
        return cleaned


class EmbeddingVector(BaseModel):
    """Single embedding vector with stable index in the batch."""

    index: int = Field(ge=0)
    values: list[float] = Field(min_length=1)

    model_config = {"frozen": True}


class EmbeddingResult(BaseModel):
    """Batch embedding response."""

    vectors: list[EmbeddingVector]
    model: str
    dimensions: int
    provider: EmbeddingProviderKind
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)

    model_config = {"frozen": True}

    @property
    def vector_values(self) -> list[list[float]]:
        """Return raw float lists ordered by ``index``."""
        ordered = sorted(self.vectors, key=lambda item: item.index)
        return [item.values for item in ordered]
