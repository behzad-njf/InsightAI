"""Unit tests for API authentication (Phase 7.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from insightai.domain.exceptions import ConfigurationError, InvalidCredentialsError
from insightai.domain.models.auth import ApiAuthMode, ApiKeyAuthSource
from insightai.infrastructure.auth.service import authenticate_request
from tests.conftest import make_settings


def test_none_mode_allows_anonymous() -> None:
    settings = make_settings(api_auth_mode=ApiAuthMode.NONE)
    principal = authenticate_request(settings, authorization=None, api_key_header=None)
    assert principal.subject == "anonymous"
    assert principal.auth_method == ApiAuthMode.NONE


def test_api_key_header_valid() -> None:
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_keys="secret-a,secret-b",
    )
    principal = authenticate_request(
        settings,
        authorization=None,
        api_key_header="secret-b",
    )
    assert principal.auth_method == ApiAuthMode.API_KEY
    assert principal.subject.startswith("api_key_")


def test_api_key_bearer_valid() -> None:
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_keys="my-key",
    )
    principal = authenticate_request(
        settings,
        authorization="Bearer my-key",
        api_key_header=None,
    )
    assert principal.auth_method == ApiAuthMode.API_KEY


def test_api_key_missing_raises() -> None:
    settings = make_settings(api_auth_mode=ApiAuthMode.API_KEY, api_keys="only-one")
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(settings, authorization=None, api_key_header=None)


def test_api_key_invalid_raises() -> None:
    settings = make_settings(api_auth_mode=ApiAuthMode.API_KEY, api_keys="valid")
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(settings, authorization="Bearer wrong", api_key_header=None)


def test_jwt_valid() -> None:
    secret = "test-jwt-secret"
    token = jwt.encode(
        {
            "sub": "user-42",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    settings = make_settings(api_auth_mode=ApiAuthMode.JWT, jwt_secret=secret)
    principal = authenticate_request(
        settings,
        authorization=f"Bearer {token}",
        api_key_header=None,
    )
    assert principal.subject == "user-42"
    assert principal.auth_method == ApiAuthMode.JWT


def test_jwt_expired_raises() -> None:
    secret = "test-jwt-secret"
    token = jwt.encode(
        {
            "sub": "user-42",
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    settings = make_settings(api_auth_mode=ApiAuthMode.JWT, jwt_secret=secret)
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(
            settings,
            authorization=f"Bearer {token}",
            api_key_header=None,
        )


def test_production_rejects_auth_none() -> None:
    from insightai.infrastructure.config.settings import AppEnvironment

    with pytest.raises(ValueError, match="API_AUTH_MODE"):
        make_settings(env=AppEnvironment.PRODUCTION, api_auth_mode=ApiAuthMode.NONE)


def test_database_api_key_valid(api_key_store) -> None:
    from insightai.domain.models.api_key import CreateApiKeyRequest

    created = api_key_store.create(CreateApiKeyRequest(label="HTTP client", roles=["analyst"]))
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
        api_keys=None,
    )
    principal = authenticate_request(
        settings,
        authorization=f"Bearer {created.secret}",
        api_key_header=None,
        api_key_store=api_key_store,
    )
    assert principal.api_key_id == created.api_key.id
    assert principal.subject == "HTTP client"
    assert principal.has_role("analyst")


def test_database_source_env_key_rejected_when_empty_env(api_key_store) -> None:
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
        api_keys=None,
    )
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(
            settings,
            authorization="Bearer legacy-env-key",
            api_key_header=None,
            api_key_store=api_key_store,
        )


def test_both_prefers_database_over_env(api_key_store) -> None:
    from insightai.domain.models.api_key import CreateApiKeyRequest

    created = api_key_store.create(CreateApiKeyRequest(label="DB wins", roles=["admin"]))
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.BOTH,
        api_keys="shared-env-key",
    )
    principal = authenticate_request(
        settings,
        authorization=f"Bearer {created.secret}",
        api_key_header=None,
        api_key_store=api_key_store,
    )
    assert principal.subject == "DB wins"
    assert principal.api_key_id is not None

    env_principal = authenticate_request(
        settings,
        authorization="Bearer shared-env-key",
        api_key_header=None,
        api_key_store=api_key_store,
    )
    assert env_principal.api_key_id is None
    assert env_principal.subject.startswith("api_key_")


def test_database_source_without_store_raises() -> None:
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
    )
    with pytest.raises(ConfigurationError, match="app database"):
        authenticate_request(
            settings,
            authorization="Bearer iai_anything",
            api_key_header=None,
            api_key_store=None,
        )


def test_env_only_skips_database_even_if_store_matches(api_key_store) -> None:
    from insightai.domain.models.api_key import CreateApiKeyRequest

    created = api_key_store.create(CreateApiKeyRequest(label="Skipped", roles=["analyst"]))
    settings = make_settings(
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.ENV,
        api_keys="only-env",
    )
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(
            settings,
            authorization=f"Bearer {created.secret}",
            api_key_header=None,
            api_key_store=api_key_store,
        )
