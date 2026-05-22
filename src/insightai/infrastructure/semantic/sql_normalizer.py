"""SQL canonicalization for trusted asset matching (Phase 11)."""

from __future__ import annotations

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import _normalize_question_phrase
from insightai.infrastructure.security.sqlglot_integration import (
    SqlglotParseError,
    canonicalize_sql,
    parse_sql,
)


def normalize_sql(sql: str, *, kind: DatabaseKind) -> str | None:
    """
    Parse and render SQL in a stable canonical form for equality checks.

    Returns ``None`` when the statement cannot be parsed (matcher skips normalized compare).
    """
    text = sql.strip()
    if not text:
        return None
    try:
        expression = parse_sql(text, kind=kind)
    except SqlglotParseError:
        return None
    return canonicalize_sql(expression, kind=kind).strip()


def normalize_question(question: str) -> str:
    """Collapse whitespace, lowercase, strip trailing sentence punctuation."""
    return _normalize_question_phrase(question)
