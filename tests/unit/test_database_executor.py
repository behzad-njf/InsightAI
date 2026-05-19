"""Unit tests for read-only query executor (SQLite in-memory)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from insightai.domain.exceptions import (
    DatabaseQueryError,
    DatabaseQueryTimeoutError,
    ReadOnlySQLViolationError,
)
from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions
from insightai.infrastructure.database.health_check import DatabaseHealthCheck
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator


@pytest.fixture
def sqlite_executor() -> ReadOnlyQueryExecutor:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)")
        )
        conn.execute(
            text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')")
        )
        conn.execute(
            text("INSERT INTO accounts_user (id, email) VALUES (2, 'b@test.com')")
        )
    return ReadOnlyQueryExecutor(
        engine,
        create_sql_safety_validator(kind=DatabaseKind.SQLITE),
        kind=DatabaseKind.SQLITE,
    )


def test_executor_select_returns_rows(sqlite_executor: ReadOnlyQueryExecutor) -> None:
    result = sqlite_executor.execute(
        "SELECT id, email FROM accounts_user ORDER BY id",
    )
    assert result.row_count == 2
    assert result.rows[0]["email"] == "a@test.com"
    assert result.columns[0].name == "id"
    assert result.execution_time_ms is not None


def test_executor_rejects_delete(sqlite_executor: ReadOnlyQueryExecutor) -> None:
    with pytest.raises(ReadOnlySQLViolationError):
        sqlite_executor.execute("DELETE FROM accounts_user WHERE id = 1")


def test_executor_truncates_rows(sqlite_executor: ReadOnlyQueryExecutor) -> None:
    result = sqlite_executor.execute(
        "SELECT id FROM accounts_user ORDER BY id",
        options=QueryExecutionOptions(max_rows=1),
    )
    assert result.row_count == 1
    assert result.truncated is True


def test_executor_rejects_invalid_sql(sqlite_executor: ReadOnlyQueryExecutor) -> None:
    with pytest.raises(DatabaseQueryError):
        sqlite_executor.execute("SELECT missing_column FROM accounts_user")


def test_executor_maps_dbapi_timeout_to_database_query_timeout(
    sqlite_executor: ReadOnlyQueryExecutor,
) -> None:
    dbapi_exc = DBAPIError(
        "SELECT ...",
        {},
        Exception("statement timed out"),
    )
    with patch.object(sqlite_executor._engine, "connect") as mock_connect:
        connection = MagicMock()
        mock_connect.return_value.__enter__.return_value = connection
        connection.execution_options.return_value.execute.side_effect = dbapi_exc

        with pytest.raises(DatabaseQueryTimeoutError) as exc_info:
            sqlite_executor.execute(
                "SELECT id FROM accounts_user",
                options=QueryExecutionOptions(max_rows=10, timeout_seconds=5),
            )

    assert "5" in str(exc_info.value)


def test_health_check_sqlite(sqlite_executor: ReadOnlyQueryExecutor) -> None:
    health = DatabaseHealthCheck(
        sqlite_executor._engine,
        DatabaseKind.SQLITE,
    )
    status = health.check()
    assert status.healthy is True
    assert status.latency_ms is not None
