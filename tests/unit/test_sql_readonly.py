"""Unit tests for read-only SQL validation."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import ReadOnlySQLViolationError
from insightai.domain.models.sql import SQLStatementKind
from insightai.infrastructure.security.sql_readonly import SQLReadOnlyValidator


@pytest.fixture
def validator() -> SQLReadOnlyValidator:
    return SQLReadOnlyValidator()


def test_accepts_simple_select(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("SELECT id, email FROM accounts_user WHERE is_active = 1")
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT
    assert result.normalized_sql is not None
    assert "accounts_user" in result.normalized_sql


def test_accepts_with_cte(validator: SQLReadOnlyValidator) -> None:
    sql = """
    WITH active_users AS (
        SELECT id FROM accounts_user WHERE is_active = 1
    )
    SELECT * FROM active_users
    """
    result = validator.validate(sql)
    assert result.is_valid is True


def test_rejects_delete(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("DELETE FROM accounts_user WHERE id = 1")
    assert result.is_valid is False
    assert any("DELETE" in v.upper() for v in result.violations)


def test_rejects_insert(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("INSERT INTO accounts_user (email) VALUES ('a@b.c')")
    assert result.is_valid is False


def test_rejects_drop(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("DROP TABLE accounts_user")
    assert result.is_valid is False


def test_rejects_select_into(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("SELECT * INTO #tmp FROM accounts_user")
    assert result.is_valid is False
    assert any("SELECT INTO" in v.upper() for v in result.violations)


def test_rejects_multiple_statements(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("SELECT 1; SELECT 2")
    assert result.is_valid is False
    assert any("Multiple" in v for v in result.violations)


def test_rejects_exec(validator: SQLReadOnlyValidator) -> None:
    result = validator.validate("EXEC sp_help")
    assert result.is_valid is False


def test_strips_line_comments(validator: SQLReadOnlyValidator) -> None:
    sql = "-- evil\nSELECT 1"
    result = validator.validate(sql)
    assert result.is_valid is True


def test_select_with_string_literal(validator: SQLReadOnlyValidator) -> None:
    sql = "SELECT 'active' AS status FROM accounts_user"
    result = validator.validate(sql)
    assert result.is_valid is True


def test_comment_stripping_allows_select(validator: SQLReadOnlyValidator) -> None:
    """Line comments are removed before keyword analysis."""
    sql = "-- previous query removed\nSELECT 1"
    result = validator.validate(sql)
    assert result.is_valid is True


def test_assert_readonly_raises(validator: SQLReadOnlyValidator) -> None:
    with pytest.raises(ReadOnlySQLViolationError):
        validator.assert_readonly("UPDATE accounts_user SET email = 'x'")
