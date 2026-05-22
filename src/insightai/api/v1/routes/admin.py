"""Admin API routes — key management metadata (Phase 16.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from insightai.api.auth.admin import require_admin_role
from insightai.api.rate_limit import enforce_rate_limit
from insightai.api.schemas.admin import ApiKeyListItem, ApiKeyListResponse
from insightai.domain.models.auth import AuthenticatedPrincipal

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(enforce_rate_limit)],
)


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    request: Request,
    _admin: AuthenticatedPrincipal = Depends(require_admin_role),
    include_revoked: bool = False,
) -> ApiKeyListResponse:
    """
    List platform API keys (no secrets).

    Requires an API key with the ``admin`` role.
    """
    app_db = request.app.state.app_database
    keys = app_db.api_key_store.list_keys(include_revoked=include_revoked)
    items = [
        ApiKeyListItem(
            id=key.id,
            key_prefix=key.key_prefix,
            label=key.label,
            roles=list(key.roles),
            attributes=key.attributes,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            active=key.is_active,
        )
        for key in keys
    ]
    return ApiKeyListResponse(keys=items, count=len(items))
