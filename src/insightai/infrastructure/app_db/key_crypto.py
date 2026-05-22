"""Bcrypt hashing for API key secrets at rest (Phase 16.3)."""

from __future__ import annotations

import bcrypt


def hash_api_key_secret(plain: str) -> str:
    """Return a bcrypt hash string for storage."""
    digest = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_api_key_secret(plain: str, hashed: str) -> bool:
    """Constant-time compare of plaintext token against stored hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
