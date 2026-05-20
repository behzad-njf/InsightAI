"""Cache key helpers (Phase 9)."""

from __future__ import annotations


def qualify_key(prefix: str, key: str) -> str:
    """Apply the configured namespace prefix unless ``key`` already has it."""
    if key.startswith(prefix):
        return key
    return f"{prefix}{key}"


def build_cache_key(*parts: str) -> str:
    """Join logical key segments with ``:`` (caller still applies prefix via adapter)."""
    return ":".join(part.strip() for part in parts if part.strip())
