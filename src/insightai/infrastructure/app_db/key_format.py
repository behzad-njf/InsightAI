"""API key token format and generation (Phase 16.3)."""

from __future__ import annotations

import re
import secrets

KEY_TOKEN_PREFIX = "iai_"
_PREFIX_LEN = 12
_SECRET_LEN = 32

_BODY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def generate_key_prefix() -> str:
    """Public lookup prefix (stored in DB), fixed width."""
    return secrets.token_urlsafe(9)[:_PREFIX_LEN]


def generate_key_secret() -> str:
    """Secret segment shown once to the operator."""
    return secrets.token_urlsafe(_SECRET_LEN)[:_SECRET_LEN]


def build_api_key_token(*, key_prefix: str, secret: str) -> str:
    return f"{KEY_TOKEN_PREFIX}{key_prefix}_{secret}"


def parse_api_key_token(token: str) -> tuple[str, str] | None:
    """
    Split a presented token into ``(key_prefix, full_token)``.

    Format: ``iai_<12-char prefix>_<secret>`` — secret may contain ``_`` and ``-``.
    """
    stripped = token.strip()
    if not stripped.startswith(KEY_TOKEN_PREFIX):
        return None
    body = stripped[len(KEY_TOKEN_PREFIX) :]
    if len(body) < _PREFIX_LEN + 2 or body[_PREFIX_LEN] != "_":
        return None
    prefix = body[:_PREFIX_LEN]
    secret = body[_PREFIX_LEN + 1 :]
    if len(secret) < 16:
        return None
    if not _BODY_PATTERN.match(prefix) or not _BODY_PATTERN.match(secret):
        return None
    return prefix, stripped
