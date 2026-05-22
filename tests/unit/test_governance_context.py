"""Unit tests for governance context (Phase 16.5)."""

from __future__ import annotations

from insightai.domain.models.api_key import ApiKey, PlatformRole
from insightai.domain.models.auth import ApiAuthMode, AuthenticatedPrincipal
from insightai.domain.models.governance import GovernanceContext


def test_from_authenticated_principal_db_key() -> None:
    from datetime import UTC, datetime

    principal = AuthenticatedPrincipal.from_api_key(
        ApiKey(
            id="00000000-0000-0000-0000-000000000010",
            key_prefix="prefix123456",
            label="Campus analyst",
            roles=[PlatformRole.ANALYST.value],
            attributes={"campus_ids": ["1", "2"]},
            created_at=datetime.now(UTC),
        ),
    )
    ctx = GovernanceContext.from_authenticated_principal(principal)
    assert ctx is not None
    assert ctx.api_key_id == principal.api_key_id
    assert ctx.has_role("analyst")
    assert ctx.attribute_values("campus_ids") == ("1", "2")


def test_from_authenticated_principal_anonymous() -> None:
    assert GovernanceContext.from_authenticated_principal(
        AuthenticatedPrincipal.anonymous(),
    ) is None


def test_principal_has_admin_role() -> None:
    principal = AuthenticatedPrincipal(
        subject="admin-user",
        auth_method=ApiAuthMode.API_KEY,
        roles=("admin",),
    )
    assert principal.has_role("admin")
