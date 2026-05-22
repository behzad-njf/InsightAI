"""Unit tests for SqlApiKeyStore (Phase 16.3)."""

from __future__ import annotations

from insightai.domain.models.api_key import CreateApiKeyRequest, PlatformRole
from insightai.infrastructure.app_db.key_format import parse_api_key_token


def test_create_verify_revoke_list(api_key_store) -> None:
    created = api_key_store.create(
        CreateApiKeyRequest(
            label="Example integration",
            roles=[PlatformRole.ANALYST.value],
            attributes={"campus_ids": ["1"]},
        ),
    )
    assert created.secret.startswith("iai_")
    assert parse_api_key_token(created.secret) is not None

    verified = api_key_store.verify(created.secret)
    assert verified is not None
    assert verified.id == created.api_key.id
    assert verified.label == "Example integration"

    keys = api_key_store.list_keys()
    assert len(keys) == 1

    assert api_key_store.revoke(key_id=created.api_key.id) is True
    assert api_key_store.verify(created.secret) is None

    assert api_key_store.list_keys() == []
    revoked_list = api_key_store.list_keys(include_revoked=True)
    assert len(revoked_list) == 1
    assert revoked_list[0].is_revoked


def test_verify_rejects_wrong_secret(api_key_store) -> None:
    created = api_key_store.create(CreateApiKeyRequest(label="Test key", roles=["analyst"]))
    assert api_key_store.verify("iai_wrong_prefix_wrongsecretvalue000000000") is None
    assert api_key_store.verify(created.secret + "x") is None
