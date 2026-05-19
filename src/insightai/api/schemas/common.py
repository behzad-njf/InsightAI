"""Shared API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = Field(description="Service status, e.g. ok")
    version: str


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    status: str = Field(description="ready | degraded")
    version: str
    database: DatabaseHealthResponse | None = None


class DatabaseHealthResponse(BaseModel):
    healthy: bool
    kind: str
    latency_ms: float | None = None
    message: str | None = None
