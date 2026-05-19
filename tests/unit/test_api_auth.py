"""Unit tests for API authentication (Phase 7.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from insightai.domain.exceptions import InvalidCredentialsError
from insightai.domain.models.auth import ApiAuthMode
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
