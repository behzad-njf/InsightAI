"""Tests for API key token format helpers."""

from __future__ import annotations

from insightai.infrastructure.app_db.key_format import (
    build_api_key_token,
    generate_key_prefix,
    generate_key_secret,
    parse_api_key_token,
)


def test_generate_and_parse_roundtrip() -> None:
    prefix = generate_key_prefix()
    secret = generate_key_secret()
    token = build_api_key_token(key_prefix=prefix, secret=secret)
    parsed = parse_api_key_token(token)
    assert parsed is not None
    assert parsed[0] == prefix
    assert parsed[1] == token


def test_parse_rejects_invalid_tokens() -> None:
    assert parse_api_key_token("") is None
    assert parse_api_key_token("not-a-key") is None
    assert parse_api_key_token("iai_short") is None
