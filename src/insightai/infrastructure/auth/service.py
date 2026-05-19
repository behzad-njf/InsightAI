"""Validate API keys and JWTs from request headers."""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, Any

from insightai.domain.exceptions import ConfigurationError, InvalidCredentialsError
from insightai.domain.models.auth import ApiAuthMode, AuthenticatedPrincipal

if TYPE_CHECKING:
    from insightai.infrastructure.config.settings import Settings


def authenticate_request(
    settings: Settings,
    *,
    authorization: str | None,
    api_key_header: str | None,
) -> AuthenticatedPrincipal:
    """
    Resolve the caller identity from headers.

    Supports ``X-API-Key`` and ``Authorization: Bearer <token>``.
    """
    if settings.api_auth_mode == ApiAuthMode.NONE:
        return AuthenticatedPrincipal.anonymous()

    token = _extract_bearer_token(authorization)
    if settings.api_auth_mode == ApiAuthMode.API_KEY:
        candidate = (api_key_header or "").strip() or token
        if not candidate:
            raise InvalidCredentialsError("API key required (X-API-Key or Bearer token).")
        if not _is_valid_api_key(settings, candidate):
            raise InvalidCredentialsError("Invalid API key.")
        return AuthenticatedPrincipal(
            subject=_api_key_subject(settings, candidate),
            auth_method=ApiAuthMode.API_KEY,
        )

    if settings.api_auth_mode == ApiAuthMode.JWT:
        if not token:
            raise InvalidCredentialsError("Bearer JWT required.")
        payload = _decode_jwt(settings, token)
        subject = str(payload.get("sub", "")).strip()
        if not subject:
            raise InvalidCredentialsError("JWT missing sub claim.")
        return AuthenticatedPrincipal(subject=subject, auth_method=ApiAuthMode.JWT)

    msg = f"Unsupported API auth mode: {settings.api_auth_mode}"
    raise ConfigurationError(msg)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, param = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    stripped = param.strip()
    return stripped or None


def _is_valid_api_key(settings: Settings, candidate: str) -> bool:
    keys = settings.parsed_api_keys()
    if not keys:
        raise ConfigurationError(
            "API key auth is enabled but INSIGHTAI_API_KEYS is empty.",
        )
    return any(hmac.compare_digest(candidate, key) for key in keys)


def _api_key_subject(settings: Settings, candidate: str) -> str:
    """Stable subject label for logging (not the secret itself)."""
    keys = settings.parsed_api_keys()
    for index, key in enumerate(keys):
        if hmac.compare_digest(candidate, key):
            return f"api_key_{index + 1}"
    return "api_key"


def _decode_jwt(settings: Settings, token: str) -> dict[str, Any]:
    secret = settings.require_jwt_secret()
    try:
        import jwt
    except ImportError as exc:
        msg = "JWT auth requires PyJWT. Install with: pip install PyJWT"
        raise ConfigurationError(msg) from exc

    options: dict[str, Any] = {"require": ["exp", "sub"]}
    decode_kwargs: dict[str, Any] = {
        "algorithms": [settings.jwt_algorithm],
        "options": options,
    }
    if settings.jwt_audience:
        decode_kwargs["audience"] = settings.jwt_audience
    if settings.jwt_issuer:
        decode_kwargs["issuer"] = settings.jwt_issuer

    try:
        payload: dict[str, Any] = jwt.decode(token, secret, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise InvalidCredentialsError("Invalid or expired JWT.") from exc
    return payload
