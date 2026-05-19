"""FastAPI dependency for config-driven API authentication (Phase 7.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from insightai.api.deps import get_settings
from insightai.domain.models.auth import AuthenticatedPrincipal
from insightai.infrastructure.auth.service import authenticate_request
from insightai.infrastructure.config.settings import Settings


async def require_api_auth(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> AuthenticatedPrincipal:
    """
    Validate API key or JWT when ``INSIGHTAI_API_AUTH_MODE`` is enabled.

    Public routes (health, smoke LLM) omit this dependency.
    """
    principal = authenticate_request(
        settings,
        authorization=authorization,
        api_key_header=x_api_key,
    )
    request.state.principal = principal
    return principal
