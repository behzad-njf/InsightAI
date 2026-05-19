"""Post-process LLM-generated SQL — extract, normalize, reject multi-statement, validate."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from insightai.domain.exceptions import SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.ports.sql_safety import ISQLSafetyValidator
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator

_SQL_FENCE_RE = re.compile(
    r"```(?:sql)?\s*\n?(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)

# Semicolon followed by another statement (not trailing terminator only).
_MULTI_STATEMENT_RE = re.compile(r";\s*\S")

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


@dataclass(frozen=True)
class PostprocessedSQL:
    """Cleaned SQL ready for safety checks and execution."""

    sql: str
    warnings: list[str] = field(default_factory=list)


def extract_sql_text(raw: str) -> str:
    """
    Return executable SQL from model output.

    Strips optional ```sql fences and outer whitespace.
    """
    text = raw.strip()
    if not text:
        return ""

    fence_match = _SQL_FENCE_RE.search(text)
    if fence_match:
        return fence_match.group(1).strip()

    # Whole string wrapped in a single fence without regex match edge cases
    if text.lower().startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            inner = lines[1:-1] if lines[0].strip().startswith("```") else lines
            return "\n".join(inner).strip()

    return text


def strip_sql_comments(sql: str) -> str:
    without_block = _BLOCK_COMMENT_RE.sub(" ", sql)
    return _LINE_COMMENT_RE.sub(" ", without_block)


def normalize_sql_whitespace(sql: str) -> str:
    """Collapse runs of whitespace to single spaces (single-line form)."""
    return re.sub(r"\s+", " ", sql).strip()


def assert_single_statement(sql: str) -> None:
    """Raise if more than one SQL statement is present."""
    cleaned = strip_sql_comments(sql).strip()
    body = cleaned.rstrip(";").strip()
    if body and _MULTI_STATEMENT_RE.search(body):
        msg = "Multiple SQL statements are not allowed."
        raise SQLGenerationRejectedError(msg, sql=sql, violations=[msg])


def postprocess_generated_sql(
    raw_sql: str,
    *,
    validator: ISQLSafetyValidator | None = None,
    database_kind: DatabaseKind | None = None,
    settings: Settings | None = None,
    enforce_readonly: bool = True,
) -> PostprocessedSQL:
    """
    Clean and validate generated SQL.

    Steps:
    1. Extract from markdown fences if present
    2. Strip comments and normalize whitespace
    3. Reject multi-statement scripts
    4. Run composite read-only validator (keyword + AST) when ``enforce_readonly``.
       Uses ``database_kind`` for sqlglot dialect when no explicit ``validator``.

    Raises:
        SQLGenerationRejectedError: Empty-after-clean, multi-statement, or failed validation.
    """
    extracted = extract_sql_text(raw_sql)
    if not extracted:
        return PostprocessedSQL(sql="")

    assert_single_statement(extracted)

    comment_stripped = strip_sql_comments(extracted)
    normalized = normalize_sql_whitespace(comment_stripped)
    if not normalized:
        msg = "SQL is empty after removing comments."
        raise SQLGenerationRejectedError(msg, sql=raw_sql, violations=[msg])

    warnings: list[str] = []
    if not enforce_readonly:
        return PostprocessedSQL(sql=normalized, warnings=warnings)

    safety = validator or create_sql_safety_validator(
        kind=database_kind,
        settings=settings or get_settings(),
    )
    validation = safety.validate(normalized)
    warnings.extend(validation.warnings)

    if not validation.is_valid:
        reason = "; ".join(validation.violations) or "Generated SQL failed read-only validation."
        raise SQLGenerationRejectedError(
            reason,
            sql=normalized,
            violations=list(validation.violations),
        )

    final_sql = validation.normalized_sql or normalized
    return PostprocessedSQL(sql=final_sql, warnings=warnings)
