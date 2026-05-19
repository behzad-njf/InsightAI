"""Tests for sqlglot dialect mapping and parse helpers (Phase 4.1)."""

from __future__ import annotations

import pytest
from sqlglot import exp

from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.security.sqlglot_integration import (
    SQLGLOT_DIALECT_BY_KIND,
    SqlglotParseError,
    canonicalize_sql,
    is_select_expression,
    parse_sql,
    sqlglot_dialect_for,
)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DatabaseKind.MSSQL, "tsql"),
        (DatabaseKind.POSTGRESQL, "postgres"),
        (DatabaseKind.SQLITE, "sqlite"),
    ],
)
def test_sqlglot_dialect_for_kind(kind: DatabaseKind, expected: str) -> None:
    assert sqlglot_dialect_for(kind) == expected
    assert SQLGLOT_DIALECT_BY_KIND[kind] == expected


def test_parse_mssql_select_top() -> None:
    expr = parse_sql(
        "SELECT TOP 10 id FROM dbo.accounts_user",
        kind=DatabaseKind.MSSQL,
    )
    assert isinstance(expr, exp.Select)
    sql = canonicalize_sql(expr, kind=DatabaseKind.MSSQL)
    assert "TOP" in sql.upper()
    assert is_select_expression(expr)


def test_parse_postgres_select_limit() -> None:
    expr = parse_sql(
        "SELECT id FROM accounts_user LIMIT 10",
        kind=DatabaseKind.POSTGRESQL,
    )
    assert is_select_expression(expr)
    sql = canonicalize_sql(expr, kind=DatabaseKind.POSTGRESQL)
    assert "LIMIT" in sql.upper()


def test_parse_sqlite_select() -> None:
    expr = parse_sql("SELECT 1 AS n", kind=DatabaseKind.SQLITE)
    assert is_select_expression(expr)


def test_parse_with_cte_mssql() -> None:
    sql = "WITH active AS (SELECT id FROM accounts_user WHERE is_active = 1) SELECT id FROM active"
    expr = parse_sql(sql, kind=DatabaseKind.MSSQL)
    # sqlglot attaches CTEs to Select (``with`` arg), not a top-level With node.
    assert isinstance(expr, exp.Select)
    assert is_select_expression(expr)


def test_parse_rejects_empty() -> None:
    with pytest.raises(SqlglotParseError, match="empty"):
        parse_sql("   ", kind=DatabaseKind.SQLITE)


def test_parse_rejects_multiple_statements() -> None:
    with pytest.raises(SqlglotParseError, match="Multiple"):
        parse_sql("SELECT 1; SELECT 2", kind=DatabaseKind.POSTGRESQL)


def test_parse_rejects_invalid_syntax() -> None:
    with pytest.raises(SqlglotParseError):
        parse_sql("SELEC 1", kind=DatabaseKind.SQLITE)


def test_is_select_expression_rejects_delete() -> None:
    expr = parse_sql("DELETE FROM accounts_user WHERE id = 1", kind=DatabaseKind.SQLITE)
    assert not is_select_expression(expr)
