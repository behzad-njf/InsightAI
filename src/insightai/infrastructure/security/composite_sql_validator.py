"""Composite read-only SQL validator — keyword + AST (Phase 4, step 4.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.ports.sql_safety import ISQLSafetyValidator
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.security.sql_parse_validator import SQLParseValidator
from insightai.infrastructure.security.sql_readonly import SQLReadOnlyValidator

if TYPE_CHECKING:
    from insightai.domain.models.database import DatabaseKind


class CompositeSQLValidator(ISQLSafetyValidator):
    """
    Fail-closed validator combining Phase 1 keywords and Phase 4 AST parsing.

    The AST layer (``SQLParseValidator``) is **authoritative for acceptance**: when
    parsing succeeds and the query is read-only, the result is accepted even if the
    keyword layer would false-positive (e.g. ``'DELETE'`` inside a string literal).

    When parsing fails, the AST result is returned unchanged (fail-closed). Keyword
    violations are merged only when both layers reject, to enrich error messages.
    """

    def __init__(
        self,
        *,
        parse_validator: SQLParseValidator,
        keyword_validator: SQLReadOnlyValidator | None = None,
    ) -> None:
        self._parse = parse_validator
        self._keyword = keyword_validator or SQLReadOnlyValidator()

    @property
    def database_kind(self) -> DatabaseKind:
        return self._parse.database_kind

    @property
    def parse_validator(self) -> SQLParseValidator:
        return self._parse

    @property
    def keyword_validator(self) -> SQLReadOnlyValidator:
        return self._keyword

    def validate(self, sql: str) -> SQLValidationResult:
        parse_result = self._parse.validate(sql)

        if parse_result.is_valid:
            return parse_result

        keyword_result = self._keyword.validate(sql)
        if not keyword_result.is_valid:
            return _merge_rejections(parse_result, keyword_result)

        return parse_result


def create_sql_safety_validator(
    kind: DatabaseKind | None = None,
    settings: Settings | None = None,
) -> CompositeSQLValidator:
    """
    Build the production read-only SQL validator for the configured database dialect.

    Uses ``INSIGHTAI_DATABASE_KIND`` when ``kind`` is omitted.
    """
    settings = settings or get_settings()
    db_kind = kind or settings.database_kind
    return CompositeSQLValidator(
        parse_validator=SQLParseValidator(db_kind),
        keyword_validator=SQLReadOnlyValidator(),
    )


def _merge_rejections(
    primary: SQLValidationResult,
    secondary: SQLValidationResult,
) -> SQLValidationResult:
    violations: list[str] = []
    seen: set[str] = set()
    for item in [*primary.violations, *secondary.violations]:
        if item not in seen:
            seen.add(item)
            violations.append(item)

    warnings = list(dict.fromkeys([*primary.warnings, *secondary.warnings]))

    return SQLValidationResult(
        is_valid=False,
        statement_kind=SQLStatementKind.FORBIDDEN,
        normalized_sql=None,
        violations=violations,
        warnings=warnings,
    )
