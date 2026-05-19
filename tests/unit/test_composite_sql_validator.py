"""Tests for CompositeSQLValidator (Phase 4.3)."""

from __future__ import annotations

import pytest

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.sql import SQLStatementKind
from insightai.infrastructure.security.composite_sql_validator import (
    CompositeSQLValidator,
    create_sql_safety_validator,
)
from insightai.infrastructure.security.sql_parse_validator import SQLParseValidator
from insightai.infrastructure.security.sql_readonly import SQLReadOnlyValidator


@pytest.fixture
def composite() -> CompositeSQLValidator:
    return create_sql_safety_validator(kind=DatabaseKind.SQLITE)


def test_factory_returns_composite() -> None:
    validator = create_sql_safety_validator(kind=DatabaseKind.MSSQL)
    assert isinstance(validator, CompositeSQLValidator)
    assert validator.database_kind == DatabaseKind.MSSQL


def test_accepts_select(composite: CompositeSQLValidator) -> None:
    result = composite.validate("SELECT id FROM accounts_user")
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT
    assert result.normalized_sql is not None


def test_accepts_delete_in_string_literal(composite: CompositeSQLValidator) -> None:
    """AST is authoritative — keyword-only false positives must not reject."""
    sql = "SELECT 'DELETE' AS label FROM accounts_user"
    keyword = SQLReadOnlyValidator().validate(sql)
    assert keyword.is_valid is False

    result = composite.validate(sql)
    assert result.is_valid is True


def test_rejects_delete(composite: CompositeSQLValidator) -> None:
    result = composite.validate("DELETE FROM accounts_user WHERE id = 1")
    assert result.is_valid is False
    assert any("Delete" in v or "DELETE" in v.upper() for v in result.violations)


def test_rejects_multiple_statements(composite: CompositeSQLValidator) -> None:
    result = composite.validate("SELECT 1; SELECT 2")
    assert result.is_valid is False
    assert any("parse_error:" in v or "Multiple" in v for v in result.violations)


def test_rejects_select_into_mssql() -> None:
    validator = create_sql_safety_validator(kind=DatabaseKind.MSSQL)
    result = validator.validate("SELECT * INTO #tmp FROM accounts_user")
    assert result.is_valid is False


def test_phase1_blocked_still_blocked(composite: CompositeSQLValidator) -> None:
    payloads = [
        "INSERT INTO accounts_user (email) VALUES ('a@b.c')",
        "DROP TABLE accounts_user",
        "UPDATE accounts_user SET email = 'x'",
        "EXEC sp_help",
    ]
    for sql in payloads:
        result = composite.validate(sql)
        assert result.is_valid is False, sql


def test_merges_violations_when_both_reject() -> None:
    validator = CompositeSQLValidator(
        parse_validator=SQLParseValidator(DatabaseKind.SQLITE),
        keyword_validator=SQLReadOnlyValidator(),
    )
    result = validator.validate("DELETE FROM accounts_user")
    assert result.is_valid is False
    assert len(result.violations) >= 1
