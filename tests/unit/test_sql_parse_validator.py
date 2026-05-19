"""Unit tests for AST-based SQLParseValidator (Phase 4.2)."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import ReadOnlySQLViolationError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.sql import SQLStatementKind
from insightai.infrastructure.security.sql_parse_validator import SQLParseValidator


@pytest.fixture
def validator() -> SQLParseValidator:
    return SQLParseValidator(kind=DatabaseKind.SQLITE)


@pytest.fixture
def mssql_validator() -> SQLParseValidator:
    return SQLParseValidator(kind=DatabaseKind.MSSQL)


def test_accepts_simple_select(validator: SQLParseValidator) -> None:
    result = validator.validate("SELECT id, email FROM accounts_user WHERE is_active = 1")
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT
    assert result.normalized_sql is not None
    assert "accounts_user" in result.normalized_sql.lower()


def test_accepts_with_cte(validator: SQLParseValidator) -> None:
    sql = """
    WITH active_users AS (
        SELECT id FROM accounts_user WHERE is_active = 1
    )
    SELECT * FROM active_users
    """
    result = validator.validate(sql)
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT


def test_accepts_union(validator: SQLParseValidator) -> None:
    result = validator.validate("SELECT 1 AS n UNION SELECT 2 AS n")
    assert result.is_valid is True


def test_accepts_explain(validator: SQLParseValidator) -> None:
    result = validator.validate("EXPLAIN SELECT 1")
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT
    assert any("EXPLAIN" in w for w in result.warnings)


def test_select_with_delete_in_string_literal(validator: SQLParseValidator) -> None:
    """AST validation must not false-positive on keywords inside string literals."""
    sql = "SELECT 'DELETE' AS label, 'DROP TABLE' AS hint FROM accounts_user"
    result = validator.validate(sql)
    assert result.is_valid is True
    assert result.statement_kind == SQLStatementKind.SELECT


def test_rejects_delete(validator: SQLParseValidator) -> None:
    result = validator.validate("DELETE FROM accounts_user WHERE id = 1")
    assert result.is_valid is False
    assert any(v.startswith("forbidden_ast:Delete") for v in result.violations)


def test_rejects_insert(validator: SQLParseValidator) -> None:
    result = validator.validate("INSERT INTO accounts_user (email) VALUES ('a@b.c')")
    assert result.is_valid is False
    assert any("Insert" in v for v in result.violations)


def test_rejects_drop(validator: SQLParseValidator) -> None:
    result = validator.validate("DROP TABLE accounts_user")
    assert result.is_valid is False


def test_rejects_select_into_mssql(mssql_validator: SQLParseValidator) -> None:
    result = mssql_validator.validate("SELECT * INTO #tmp FROM accounts_user")
    assert result.is_valid is False
    assert any("Into" in v for v in result.violations)


def test_rejects_write_cte(validator: SQLParseValidator) -> None:
    sql = "WITH staged AS (INSERT INTO accounts_user (email) VALUES ('x')) SELECT 1"
    result = validator.validate(sql)
    assert result.is_valid is False
    assert any("Insert" in v for v in result.violations)


def test_rejects_multiple_statements(validator: SQLParseValidator) -> None:
    result = validator.validate("SELECT 1; SELECT 2")
    assert result.is_valid is False
    assert any(v.startswith("parse_error:") for v in result.violations)


def test_rejects_exec_as_command(validator: SQLParseValidator) -> None:
    result = validator.validate("CALL proc()")
    assert result.is_valid is False
    assert any("Command" in v for v in result.violations)


def test_rejects_exec_mssql(mssql_validator: SQLParseValidator) -> None:
    result = mssql_validator.validate("EXEC sp_help")
    assert result.is_valid is False
    assert any("Execute" in v or "forbidden_statement" in v for v in result.violations)


def test_rejects_for_update_postgres() -> None:
    validator = SQLParseValidator(kind=DatabaseKind.POSTGRESQL)
    result = validator.validate("SELECT id FROM accounts_user FOR UPDATE")
    assert result.is_valid is False
    assert any(v.startswith("for_update:") for v in result.violations)


def test_rejects_information_schema(validator: SQLParseValidator) -> None:
    validator_pg = SQLParseValidator(kind=DatabaseKind.POSTGRESQL)
    result = validator_pg.validate("SELECT table_name FROM information_schema.tables")
    assert result.is_valid is False
    assert any(v.startswith("system_catalog:") for v in result.violations)


def test_rejects_sys_objects_mssql(mssql_validator: SQLParseValidator) -> None:
    result = mssql_validator.validate("SELECT name FROM sys.objects")
    assert result.is_valid is False
    assert any(v.startswith("system_catalog:") for v in result.violations)


def test_rejects_invalid_syntax(validator: SQLParseValidator) -> None:
    result = validator.validate("SELEC 1")
    assert result.is_valid is False
    assert any(v.startswith("parse_error:") for v in result.violations)


def test_assert_readonly_raises(validator: SQLParseValidator) -> None:
    with pytest.raises(ReadOnlySQLViolationError) as exc_info:
        validator.assert_readonly("UPDATE accounts_user SET email = 'x'")
    assert "forbidden_ast:Update" in str(exc_info.value.reason)


def test_mssql_with_cte_and_top(mssql_validator: SQLParseValidator) -> None:
    sql = (
        "WITH active AS (SELECT id FROM accounts_user WHERE is_active = 1) "
        "SELECT TOP 10 id FROM active"
    )
    result = mssql_validator.validate(sql)
    assert result.is_valid is True
    assert result.normalized_sql is not None
    assert "TOP" in result.normalized_sql.upper()
