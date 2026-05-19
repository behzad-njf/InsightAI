"""Dialect-specific SQL helpers for multi-database support."""

from __future__ import annotations

from insightai.domain.models.database import DatabaseKind


def ping_sql(kind: DatabaseKind) -> str:  # noqa: ARG001
    """Return a lightweight connectivity probe statement."""
    return "SELECT 1"


def wrap_with_row_cap(sql: str, kind: DatabaseKind, limit: int) -> str:
    """
    Wrap user SQL to cap rows at the database level when possible.

    Fetches up to `limit` rows (executor passes max_rows + 1 to detect truncation).
    """
    if limit < 1:
        msg = "Row cap limit must be at least 1."
        raise ValueError(msg)

    stripped = sql.strip().rstrip(";")
    if stripped.upper().startswith("EXPLAIN"):
        return stripped

    if kind == DatabaseKind.MSSQL:
        return f"SELECT TOP {limit} * FROM ({stripped}) AS insightai_sub"

    return f"SELECT * FROM ({stripped}) AS insightai_sub LIMIT {limit}"


def infer_kind_from_url(url: str) -> DatabaseKind | None:
    """Infer database kind from SQLAlchemy URL driver name."""
    lowered = url.lower()
    if lowered.startswith("mssql"):
        return DatabaseKind.MSSQL
    if lowered.startswith("postgresql") or lowered.startswith("postgres"):
        return DatabaseKind.POSTGRESQL
    if lowered.startswith("sqlite"):
        return DatabaseKind.SQLITE
    return None
