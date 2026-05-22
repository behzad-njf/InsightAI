"""Dialect-specific SQL helpers for multi-database support."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from insightai.domain.models.database import DatabaseKind

_SQLGLOT_READ: dict[DatabaseKind, str] = {
    DatabaseKind.MSSQL: "tsql",
    DatabaseKind.POSTGRESQL: "postgres",
    DatabaseKind.SQLITE: "sqlite",
}


def ping_sql(kind: DatabaseKind) -> str:  # noqa: ARG001
    """Return a lightweight connectivity probe statement."""
    return "SELECT 1"


def _parsed_row_limit(stripped: str, kind: DatabaseKind) -> int | None:
    """Return TOP/LIMIT already present in the query, if any."""
    read_dialect = _SQLGLOT_READ.get(kind)
    if read_dialect is None:
        return None
    try:
        expression = sqlglot.parse_one(stripped, read=read_dialect)
    except sqlglot.errors.ParseError:
        return None
    if not isinstance(expression, exp.Query):
        return None
    limit_node = expression.args.get("limit")
    if limit_node is None:
        return None
    if isinstance(limit_node, exp.Limit) and isinstance(
        limit_node.expression, exp.Literal
    ):
        if limit_node.expression.is_int:
            return int(limit_node.expression.name)
    return None


def _cap_with_sqlglot(stripped: str, kind: DatabaseKind, limit: int) -> str | None:
    """Apply TOP/LIMIT via sqlglot when the statement parses (supports WITH/CTE)."""
    read_dialect = _SQLGLOT_READ.get(kind)
    if read_dialect is None:
        return None
    try:
        expression = sqlglot.parse_one(stripped, read=read_dialect)
    except sqlglot.errors.ParseError:
        return None
    if not isinstance(expression, exp.Query):
        return None
    existing = _parsed_row_limit(stripped, kind)
    effective = min(limit, existing) if existing is not None else limit
    return expression.limit(effective).sql(dialect=read_dialect)


def wrap_with_row_cap(sql: str, kind: DatabaseKind, limit: int) -> str:
    """
    Wrap user SQL to cap rows at the database level when possible.

    Fetches up to `limit` rows (executor passes max_rows + 1 to detect truncation).

    Uses sqlglot so ``WITH`` (CTE) queries work on MSSQL — subquery wrapping
    ``SELECT TOP n * FROM (WITH ...)`` is invalid T-SQL.
    """
    if limit < 1:
        msg = "Row cap limit must be at least 1."
        raise ValueError(msg)

    stripped = sql.strip().rstrip(";")
    if stripped.upper().startswith("EXPLAIN"):
        return stripped

    capped = _cap_with_sqlglot(stripped, kind, limit)
    if capped is not None:
        return capped

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
