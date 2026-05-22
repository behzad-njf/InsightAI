"""Admin-role guard for ``/api/v1/admin/*`` routes (Phase 16.5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from insightai.api.auth.dependencies import require_api_auth
from insightai.domain.models.api_key import PlatformRole
from insightai.domain.models.auth import AuthenticatedPrincipal


async def require_admin_role(
    principal: Annotated[AuthenticatedPrincipal, Depends(require_api_auth)],
) -> AuthenticatedPrincipal:
    """Require ``admin`` role on the authenticated API key or JWT."""
    if principal.has_role(PlatformRole.ADMIN.value):
        return principal
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "FORBIDDEN",
            "message": "Admin role required for this endpoint.",
        },
    )
