"""Integration tests for SQL execution via bootstrap (in-process, SQLite)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import (
    CompositeSQLValidator,
    create_sql_safety_validator,
)
from tests.conftest import make_settings


@pytest.fixture
def executor() -> ReadOnlyQueryExecutor:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')"))
    return ReadOnlyQueryExecutor(
        engine,
        create_sql_safety_validator(kind=DatabaseKind.SQLITE),
        kind=DatabaseKind.SQLITE,
    )


def test_bootstrap_sqlite_components() -> None:
    settings = make_settings(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
    )
    components = build_database_components(settings)
    assert components.config.kind == DatabaseKind.SQLITE
    assert isinstance(components.validator, CompositeSQLValidator)
    components.engine.dispose()


def test_executor_select_via_bootstrap_pattern(executor: ReadOnlyQueryExecutor) -> None:
    result = executor.execute("SELECT id, email FROM accounts_user")
    assert result.row_count == 1
    assert result.rows[0]["email"] == "a@test.com"
