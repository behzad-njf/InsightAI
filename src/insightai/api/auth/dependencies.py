"""FastAPI dependency for config-driven API authentication (Phase 7.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from insightai.api.deps import get_settings
from insightai.domain.models.auth import AuthenticatedPrincipal
from insightai.domain.models.governance import GovernanceContext
from insightai.infrastructure.auth.service import authenticate_request
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.observability.context import bind_audit_context


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
    app_db = getattr(request.app.state, "app_database", None)
    api_key_store = app_db.api_key_store if app_db is not None else None

    principal = authenticate_request(
        settings,
        authorization=authorization,
        api_key_header=x_api_key,
        api_key_store=api_key_store,
    )
    request.state.principal = principal
    governance = GovernanceContext.from_authenticated_principal(principal)
    request.state.governance_context = governance
    bind_audit_context(
        auth_subject=principal.subject,
        api_key_id=principal.api_key_id,
    )
    request.state.auth_roles = list(principal.roles)
    return principal


def get_governance_context(request: Request) -> GovernanceContext | None:
    """Return governance context bound during auth (Phase 16.5)."""
    ctx = getattr(request.state, "governance_context", None)
    if isinstance(ctx, GovernanceContext):
        return ctx
    return None
