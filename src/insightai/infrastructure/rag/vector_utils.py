"""Shared helpers for vector stores."""

from __future__ import annotations

import math
import re

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_sql_identifier(name: str, *, label: str = "identifier") -> str:
    """Allow safe PostgreSQL table/index names (lowercase snake_case)."""
    normalized = name.strip().lower()
    if not _IDENTIFIER_PATTERN.match(normalized):
        msg = f"Invalid {label}: {name!r}"
        raise ValueError(msg)
    return normalized


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        msg = "Embedding dimensions must match for cosine similarity."
        raise ValueError(msg)
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if norm_left <= 0.0 or norm_right <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_left * norm_right)))


def vector_literal(values: list[float]) -> str:
    """Format a vector for PostgreSQL pgvector casts."""
    inner = ",".join(f"{value:.8g}" for value in values)
    return f"[{inner}]"
