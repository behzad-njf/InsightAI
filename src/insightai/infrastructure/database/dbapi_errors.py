"""Classify SQLAlchemy DBAPI errors for clearer API responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.exceptions import (
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseQueryTimeoutError,
)

if TYPE_CHECKING:
    from sqlalchemy.exc import DBAPIError


def raise_for_dbapi_error(exc: DBAPIError, *, timeout_seconds: int) -> None:
    """Map ``DBAPIError`` to domain exceptions with driver detail."""
    driver_message = str(exc.orig) if exc.orig is not None else str(exc)

    if _is_connection_error(exc):
        raise DatabaseConnectionError(
            "Could not connect to the database. Check host, port, credentials, "
            "and Docker networking (use host.docker.internal or the SQL container "
            "name when the API runs inside Docker).",
            driver_message=driver_message,
        ) from exc

    if _is_query_timeout_error(exc):
        raise DatabaseQueryTimeoutError(
            f"Query exceeded timeout of {timeout_seconds}s.",
            timeout_seconds=timeout_seconds,
            driver_message=driver_message,
        ) from exc

    raise DatabaseQueryError(driver_message) from exc


def _is_connection_error(exc: DBAPIError) -> bool:
    message = str(exc).lower()
    if _is_query_timeout_error(exc):
        return False
    markers = (
        "login failed",
        "login timeout",
        "cannot open database",
        "unable to connect",
        "could not connect",
        "connection refused",
        "named pipe",
        "network-related",
        "communication link failure",
        "server was not found",
        "handshakes before login",
        "08001",
        "08s01",
        "28000",
        "18456",
    )
    return any(marker in message for marker in markers)


def _is_query_timeout_error(exc: DBAPIError) -> bool:
    message = str(exc).lower()
    if "queuepool" in message or "pool timeout" in message:
        return False
    if any(
        phrase in message for phrase in ("login timeout", "connection timeout", "connect timeout")
    ):
        return False
    if "hyt00" in message or "query timeout" in message:
        return True
    if "timeout expired" in message:
        return "login" not in message and "connection" not in message
    if "timeout" in message or "timed out" in message:
        return "connection" not in message and "login" not in message
    return False
