"""Read-only SQL validation — keyword blocklist and statement-type checks."""

from __future__ import annotations

import re

from insightai.core.constants import (
    ALLOWED_SQL_STARTERS,
    BLOCKED_SQL_KEYWORDS,
    BLOCKED_SQL_PHRASES,
)
from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.ports.sql_safety import ISQLSafetyValidator

# Word-boundary keyword detection (handles whitespace and common delimiters).
_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(BLOCKED_SQL_KEYWORDS)) + r")\b",
    re.IGNORECASE,
)

# Strip block and line comments before analysis.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")

# Detect multiple statements (semicolon not at end of string).
_MULTI_STATEMENT = re.compile(r";\s*\S")

# First SQL token after normalization.
_FIRST_TOKEN = re.compile(r"^[(\s]*(?P<token>[A-Za-z_]+)", re.IGNORECASE)


class SQLReadOnlyValidator(ISQLSafetyValidator):
    """
    Phase 1 read-only SQL validator.

    Used inside ``CompositeSQLValidator``; prefer ``create_sql_safety_validator()``
    for application wiring.
    """

    def validate(self, sql: str) -> SQLValidationResult:
        violations: list[str] = []
        warnings: list[str] = []

        if not sql or not sql.strip():
            violations.append("SQL must not be empty.")
            return SQLValidationResult(
                is_valid=False,
                statement_kind=SQLStatementKind.FORBIDDEN,
                violations=violations,
            )

        cleaned = self._strip_comments(sql.strip())
        normalized = self._normalize_whitespace(cleaned)

        if _MULTI_STATEMENT.search(normalized.rstrip(";")):
            violations.append("Multiple SQL statements are not allowed.")

        upper = normalized.upper()

        for phrase in BLOCKED_SQL_PHRASES:
            if phrase in upper:
                violations.append(f"Disallowed SQL pattern detected: {phrase}")

        if re.search(r"\bSELECT\b", upper) and re.search(r"\bINTO\b", upper):
            violations.append("SELECT INTO is not allowed (creates new objects).")

        for match in _KEYWORD_PATTERN.finditer(normalized):
            violations.append(f"Disallowed keyword: {match.group(1).upper()}")

        starter = self._first_significant_token(normalized)
        if starter is None:
            violations.append("Could not determine SQL statement type.")
        elif starter not in ALLOWED_SQL_STARTERS:
            violations.append(
                f"Only read-only queries are allowed. Statement must start with "
                f"one of {sorted(ALLOWED_SQL_STARTERS)}; got '{starter}'."
            )
        elif starter == "EXPLAIN":
            warnings.append("EXPLAIN queries are allowed but may not return business data.")

        if starter == "WITH" and "SELECT" not in upper:
            violations.append("WITH clause must be followed by a SELECT (read-only CTE).")

        is_valid = len(violations) == 0
        statement_kind = SQLStatementKind.SELECT if is_valid else SQLStatementKind.FORBIDDEN
        if is_valid and starter == "EXPLAIN":
            statement_kind = SQLStatementKind.SELECT

        return SQLValidationResult(
            is_valid=is_valid,
            statement_kind=statement_kind,
            normalized_sql=normalized if is_valid else None,
            violations=violations,
            warnings=warnings,
        )

    @staticmethod
    def _strip_comments(sql: str) -> str:
        without_block = _BLOCK_COMMENT.sub(" ", sql)
        return _LINE_COMMENT.sub(" ", without_block)

    @staticmethod
    def _normalize_whitespace(sql: str) -> str:
        return re.sub(r"\s+", " ", sql).strip()

    @staticmethod
    def _first_significant_token(sql: str) -> str | None:
        match = _FIRST_TOKEN.match(sql)
        if not match:
            return None
        return match.group("token").upper()
