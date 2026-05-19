"""Rate limiting domain models (Phase 7.5)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RateLimitResult(BaseModel):
    """Outcome of a sliding-window rate limit check."""

    allowed: bool
    limit: int = Field(ge=1)
    remaining: int = Field(ge=0)
    retry_after_seconds: int = Field(
        default=0,
        ge=0,
        description="Seconds until the client may retry (0 when allowed).",
    )

    model_config = {"frozen": True}
