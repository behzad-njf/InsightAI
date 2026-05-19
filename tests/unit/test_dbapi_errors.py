"""Unit tests for DBAPI error classification."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import DBAPIError

from insightai.domain.exceptions import (
    DatabaseConnectionError,
    DatabaseQueryTimeoutError,
)
from insightai.infrastructure.database.dbapi_errors import raise_for_dbapi_error


def _dbapi(message: str) -> DBAPIError:
    return DBAPIError("stmt", {}, Exception(message))


def test_login_failure_maps_to_connection_error() -> None:
    with pytest.raises(DatabaseConnectionError) as exc_info:
        raise_for_dbapi_error(
            _dbapi("Login failed for user 'sa'."),
            timeout_seconds=120,
        )
    assert exc_info.value.driver_message is not None
    assert "Login failed" in exc_info.value.driver_message


def test_login_timeout_maps_to_connection_error() -> None:
    with pytest.raises(DatabaseConnectionError):
        raise_for_dbapi_error(
            _dbapi("Login timeout expired"),
            timeout_seconds=120,
        )


def test_hyt00_maps_to_query_timeout() -> None:
    with pytest.raises(DatabaseQueryTimeoutError) as exc_info:
        raise_for_dbapi_error(
            _dbapi("[HYT00] [Microsoft][ODBC Driver 17] Query timeout expired"),
            timeout_seconds=180,
        )
    assert exc_info.value.timeout_seconds == 180


def test_statement_timed_out_maps_to_query_timeout() -> None:
    with pytest.raises(DatabaseQueryTimeoutError):
        raise_for_dbapi_error(
            _dbapi("statement timed out"),
            timeout_seconds=5,
        )
