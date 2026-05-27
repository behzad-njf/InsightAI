"""Phase 12.5 — principal attribute contract and auth → governance wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from insightai.domain.models.api_key import (
    ApiKey,
    parse_attributes_arg,
    parse_attributes_json,
)
from insightai.domain.models.auth import ApiAuthMode, AuthenticatedPrincipal
from insightai.domain.models.governance import GovernanceContext
from insightai.infrastructure.governance.attribute_contract import (
    required_attributes_for_roles,
    validate_key_attributes_for_catalog,
)
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

FIXTURE_GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "governance"


def test_parse_attributes_arg_key_value_pairs() -> None:
    attrs = parse_attributes_arg("campus_ids=1,2")
    assert attrs == {"campus_ids": ["1", "2"]}


def test_parse_attributes_arg_json() -> None:
    attrs = parse_attributes_json('{"campus_ids": ["1", "2"]}')
    assert attrs == {"campus_ids": ["1", "2"]}


def test_required_attributes_for_analyst_role() -> None:
    catalog = YamlGovernancePolicyLoader(FIXTURE_GOVERNANCE_DIR).load()
    required = required_attributes_for_roles(catalog)
    assert "campus_ids" in required.get("analyst", frozenset())


def test_validate_key_missing_campus_ids() -> None:
    catalog = YamlGovernancePolicyLoader(FIXTURE_GOVERNANCE_DIR).load()
    errors = validate_key_attributes_for_catalog(["analyst"], {}, catalog)
    assert any("campus_ids" in line for line in errors)


def test_validate_key_with_campus_ids_ok() -> None:
    catalog = YamlGovernancePolicyLoader(FIXTURE_GOVERNANCE_DIR).load()
    errors = validate_key_attributes_for_catalog(
        ["analyst"],
        {"campus_ids": ["1"]},
        catalog,
    )
    assert errors == []


def test_jwt_claims_map_to_governance_context() -> None:
    principal = AuthenticatedPrincipal.from_jwt_claims(
        {
            "sub": "jwt-user",
            "roles": ["analyst"],
            "attributes": {"campus_ids": ["1", "2"]},
        },
    )
    ctx = GovernanceContext.from_authenticated_principal(principal)
    assert ctx is not None
    assert ctx.auth_method == ApiAuthMode.JWT.value
    assert ctx.has_role("analyst")
    assert ctx.attribute_values("campus_ids") == ("1", "2")


def test_api_key_principal_matches_governance_context() -> None:
    key = ApiKey(
        id="00000000-0000-0000-0000-000000000099",
        key_prefix="prefix123456",
        label="Example",
        roles=["analyst"],
        attributes={"campus_ids": ["3"]},
        created_at=datetime.now(UTC),
    )
    principal = AuthenticatedPrincipal.from_api_key(key)
    ctx = GovernanceContext.from_authenticated_principal(principal)
    assert ctx is not None
    assert ctx.api_key_id == key.id
    assert ctx.attribute_values("campus_ids") == ("3",)
