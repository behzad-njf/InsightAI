"""Admin API schemas (Phase 16.5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyListItem(BaseModel):
    id: str
    key_prefix: str
    label: str
    roles: list[str] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    active: bool = True


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyListItem]
    count: int = Field(ge=0)
