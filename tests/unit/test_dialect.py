"""Unit tests for database dialect helpers."""

from __future__ import annotations

import pytest

from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.database.dialect import (
    infer_kind_from_url,
    ping_sql,
    wrap_with_row_cap,
)


def test_ping_sql() -> None:
    assert ping_sql(DatabaseKind.MSSQL) == "SELECT 1"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("mssql+pyodbc://user:pass@host/db", DatabaseKind.MSSQL),
        ("postgresql+psycopg2://user:pass@host/db", DatabaseKind.POSTGRESQL),
        ("sqlite:///:memory:", DatabaseKind.SQLITE),
        ("unknown://host/db", None),
    ],
)
def test_infer_kind_from_url(url: str, expected: DatabaseKind | None) -> None:
    assert infer_kind_from_url(url) == expected


def test_wrap_with_row_cap_mssql() -> None:
    sql = "SELECT id FROM accounts_user"
    wrapped = wrap_with_row_cap(sql, DatabaseKind.MSSQL, 10)
    assert "SELECT TOP 10" in wrapped
    assert "insightai_sub" in wrapped


def test_wrap_with_row_cap_postgres() -> None:
    sql = "SELECT id FROM accounts_user"
    wrapped = wrap_with_row_cap(sql, DatabaseKind.POSTGRESQL, 5)
    assert wrapped.endswith("LIMIT 5")


def test_wrap_with_row_cap_explain_unchanged() -> None:
    sql = "EXPLAIN SELECT 1"
    assert wrap_with_row_cap(sql, DatabaseKind.SQLITE, 10) == sql


def test_wrap_with_row_cap_invalid_limit() -> None:
    with pytest.raises(ValueError):
        wrap_with_row_cap("SELECT 1", DatabaseKind.SQLITE, 0)
