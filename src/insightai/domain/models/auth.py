"""API authentication domain models (Phase 7.4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field


class ApiAuthMode(StrEnum):
    """How inbound API requests are authenticated."""

    NONE = "none"
    API_KEY = "api_key"
    JWT = "jwt"


class AuthenticatedPrincipal(BaseModel):
    """Caller identity attached to a request after auth."""

    subject: str = Field(description="API key label, JWT sub, or 'anonymous'.")
    auth_method: ApiAuthMode | str = Field(
        description="none when auth is disabled; otherwise api_key or jwt.",
    )

    model_config = {"frozen": True}

    @classmethod
    def anonymous(cls) -> Self:
        return cls(subject="anonymous", auth_method=ApiAuthMode.NONE)
