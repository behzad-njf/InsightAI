"""sqlglot dialect mapping and parse helpers (Phase 4, step 4.1).

Maps ``DatabaseKind`` to sqlglot read/write dialects and provides a single-statement
parse entry point for MSSQL (T-SQL), PostgreSQL, and SQLite.
"""

from __future__ import annotations

from typing import cast

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from insightai.domain.models.database import DatabaseKind

# sqlglot uses ``tsql`` for Microsoft SQL Server (not ``mssql``).
SQLGLOT_DIALECT_BY_KIND: dict[DatabaseKind, str] = {
    DatabaseKind.MSSQL: "tsql",
    DatabaseKind.POSTGRESQL: "postgres",
    DatabaseKind.SQLITE: "sqlite",
}


class SqlglotParseError(ValueError):
    """Raised when sqlglot cannot parse SQL for the configured dialect."""

    def __init__(self, message: str, *, dialect: str, sql: str) -> None:
        super().__init__(message)
        self.dialect = dialect
        self.sql = sql


def sqlglot_dialect_for(kind: DatabaseKind) -> str:
    """Return the sqlglot dialect name for a configured database kind."""
    try:
        return SQLGLOT_DIALECT_BY_KIND[kind]
    except KeyError as exc:
        msg = f"No sqlglot dialect mapping for database kind: {kind!r}"
        raise ValueError(msg) from exc


def parse_sql(
    sql: str,
    *,
    kind: DatabaseKind,
) -> exp.Expression:
    """
    Parse exactly one SQL statement for the given database kind.

    Raises:
        SqlglotParseError: On syntax errors or when more than one statement is present.
    """
    dialect = sqlglot_dialect_for(kind)
    text = sql.strip()
    if not text:
        raise SqlglotParseError("SQL must not be empty.", dialect=dialect, sql=sql)

    try:
        statements = parse(text, read=dialect)
    except ParseError as exc:
        raise SqlglotParseError(
            str(exc),
            dialect=dialect,
            sql=sql,
        ) from exc

    if not statements:
        raise SqlglotParseError(
            "No SQL statement could be parsed.",
            dialect=dialect,
            sql=sql,
        )
    if len(statements) > 1:
        raise SqlglotParseError(
            "Multiple SQL statements are not allowed.",
            dialect=dialect,
            sql=sql,
        )

    statement = statements[0]
    if statement is None:
        raise SqlglotParseError(
            "No SQL statement could be parsed.",
            dialect=dialect,
            sql=sql,
        )
    return cast("exp.Expression", statement)


def canonicalize_sql(
    expression: exp.Expression,
    *,
    kind: DatabaseKind,
) -> str:
    """Render a parsed expression as canonical SQL for the target dialect."""
    dialect = sqlglot_dialect_for(kind)
    return expression.sql(dialect=dialect)


def is_select_expression(expression: exp.Expression) -> bool:
    """True when the root expression is a read-style SELECT (includes WITH ... SELECT)."""
    if isinstance(expression, exp.Select):
        return True
    if isinstance(expression, exp.Union):
        return True
    if isinstance(expression, (exp.Subquery, exp.Query)):
        return isinstance(expression.this, exp.Select)
    # WITH wraps the final SELECT
    if isinstance(expression, exp.With):
        body = expression.this
        return isinstance(body, (exp.Select, exp.Union))
    return False
