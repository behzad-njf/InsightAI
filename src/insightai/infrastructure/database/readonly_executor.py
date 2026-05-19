"""Read-only SQL query executor using SQLAlchemy Core."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from insightai.domain.exceptions import (
    DatabaseQueryError,
    DatabaseQueryTimeoutError,
    ReadOnlySQLViolationError,
)
from insightai.domain.models.database import (
    QueryColumn,
    QueryExecutionOptions,
    QueryResult,
)
from insightai.domain.ports.database import IReadOnlyQueryExecutor
from insightai.domain.ports.sql_safety import ISQLSafetyValidator  # noqa: TC001
from insightai.infrastructure.database.dbapi_errors import raise_for_dbapi_error
from insightai.infrastructure.database.dialect import wrap_with_row_cap
from insightai.infrastructure.database.serialization import serialize_value
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.domain.models.database import DatabaseKind

logger = get_logger(__name__)


class ReadOnlyQueryExecutor(IReadOnlyQueryExecutor):
    """
    Executes validated SELECT statements and returns normalized results.

    Always runs SQL through ISQLSafetyValidator when enforce_readonly is enabled.
    """

    def __init__(
        self,
        engine: Engine,
        validator: ISQLSafetyValidator,
        *,
        kind: DatabaseKind,
        default_options: QueryExecutionOptions | None = None,
    ) -> None:
        self._engine = engine
        self._validator = validator
        self._kind = kind
        self._default_options = default_options or QueryExecutionOptions()

    @property
    def default_options(self) -> QueryExecutionOptions:
        return self._default_options

    def execute(
        self,
        sql: str,
        *,
        options: QueryExecutionOptions | None = None,
    ) -> QueryResult:
        opts = options or self._default_options
        sql_to_run = sql.strip()

        if opts.enforce_readonly:
            validation = self._validator.validate(sql_to_run)
            if not validation.is_valid:
                reason = "; ".join(validation.violations) or "SQL is not allowed."
                raise ReadOnlySQLViolationError(
                    reason,
                    sql=sql_to_run,
                    reason=reason,
                )
            sql_to_run = validation.normalized_sql or sql_to_run

        fetch_limit = opts.max_rows + 1
        wrapped_sql = wrap_with_row_cap(sql_to_run, self._kind, fetch_limit)

        logger.info(
            "sql_execution_start",
            dialect=self._kind.value,
            max_rows=opts.max_rows,
            timeout_seconds=opts.timeout_seconds,
        )

        started = time.perf_counter()
        try:
            with self._engine.connect() as connection:
                cursor = connection.execution_options(
                    timeout=opts.timeout_seconds,
                ).execute(text(wrapped_sql))
                column_names = list(cursor.keys())
                raw_rows = cursor.fetchall()
        except DBAPIError as exc:
            raise_for_dbapi_error(exc, timeout_seconds=opts.timeout_seconds)
        except SQLAlchemyError as exc:
            raise DatabaseQueryError(str(exc)) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        truncated = len(raw_rows) > opts.max_rows
        limited_rows = raw_rows[: opts.max_rows]

        columns = [
            QueryColumn(name=name, type_name=None) for name in column_names
        ]
        rows = [
            {
                column_names[i]: serialize_value(row[i])
                for i in range(len(column_names))
            }
            for row in limited_rows
        ]

        logger.info(
            "sql_execution_complete",
            row_count=len(rows),
            truncated=truncated,
            execution_time_ms=round(elapsed_ms, 2),
        )

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            execution_time_ms=round(elapsed_ms, 2),
            executed_at=datetime.now(UTC),
        )
