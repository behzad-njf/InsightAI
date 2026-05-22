"""Unit tests for Phase 16.2 API key domain models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from insightai.domain.models.api_key import (
    ApiKey,
    CreateApiKeyRequest,
    PlatformRole,
    Principal,
    parse_attributes_json,
    parse_roles_arg,
)
from insightai.domain.models.auth import ApiAuthMode


def test_parse_roles_arg_defaults_to_analyst() -> None:
    assert parse_roles_arg(None) == [PlatformRole.ANALYST.value]
    assert parse_roles_arg("admin, analyst") == ["admin", "analyst"]


def test_parse_attributes_json() -> None:
    attrs = parse_attributes_json('{"campus_ids": ["1", "2"]}')
    assert attrs == {"campus_ids": ["1", "2"]}


def test_api_key_active_revoked_expired() -> None:
    now = datetime.now(UTC)
    active = ApiKey(
        id="00000000-0000-0000-0000-000000000001",
        key_prefix="abcd1234",
        label="Example integration",
        created_at=now,
    )
    assert active.is_active

    revoked = active.model_copy(update={"revoked_at": now})
    assert not revoked.is_active

    expired = active.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    assert expired.is_expired
    assert not expired.is_active


def test_principal_from_api_key() -> None:
    now = datetime.now(UTC)
    key = ApiKey(
        id="00000000-0000-0000-0000-000000000002",
        key_prefix="prefix1234",
        label="Campus A analyst",
        roles=["analyst"],
        attributes={"campus_ids": ["1"]},
        created_at=now,
    )
    principal = Principal.from_api_key(key)
    assert principal.subject == "Campus A analyst"
    assert principal.api_key_id == key.id
    assert principal.has_role("analyst")
    assert principal.attribute_values("campus_ids") == ("1",)
    assert principal.auth_method == ApiAuthMode.API_KEY


def test_create_api_key_request_strips_label() -> None:
    req = CreateApiKeyRequest(label="  My App  ", roles=["admin"])
    assert req.label == "My App"


def test_parse_attributes_json_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="object"):
        parse_attributes_json("[1,2]")
