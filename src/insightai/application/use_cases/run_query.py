"""Execute validated read-only SQL (Phase 5.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.exceptions import DatabaseQueryError, ReadOnlySQLViolationError
from insightai.domain.models.database import QueryExecutionOptions  # noqa: TC001
from insightai.domain.models.query_execution import RunQueryRequest, RunQueryResult

if TYPE_CHECKING:
    from insightai.domain.ports.database import IReadOnlyQueryExecutor
    from insightai.domain.ports.sql_safety import ISQLSafetyValidator
    from insightai.infrastructure.config.settings import Settings


class RunQueryUseCase:
    """
    Validate and execute read-only SQL via ``IReadOnlyQueryExecutor``.

    Accepts raw SQL or Phase 3 generation output (``SQLGenerationResult`` /
    ``GenerateSQLResult``). Invalid SQL is rejected by the composite validator
    before any database round-trip (Phase 4).
    """

    def __init__(
        self,
        executor: IReadOnlyQueryExecutor,
        settings: Settings | None = None,
        *,
        sql_validator: ISQLSafetyValidator | None = None,
        execution_defaults: QueryExecutionOptions | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._executor = executor
        self._settings = settings or get_settings()
        self._sql_validator = sql_validator
        self._execution_defaults = (
            execution_defaults or self._settings.get_query_execution_options()
        )

    def execute(self, request: RunQueryRequest) -> RunQueryResult:
        try:
            sql = request.resolve_sql()
        except ValueError as exc:
            raise DatabaseQueryError(str(exc)) from exc

        options = request.to_execution_options(self._execution_defaults)

        sql_to_run = self._validate_before_execute(sql, enforce=options.enforce_readonly)

        query_result = self._executor.execute(sql_to_run, options=options)

        question: str | None = None
        if request.generate_result is not None:
            question = request.generate_result.question
        generation = request.resolved_generation()

        return RunQueryResult(
            sql=sql_to_run,
            source=request.sql_source(),
            query_result=query_result,
            question=question,
            generation=generation,
            execution_options=options,
        )

    def _validate_before_execute(self, sql: str, *, enforce: bool) -> str:
        """Run composite validator before the executor (Phase 5.2)."""
        if not enforce or self._sql_validator is None:
            return sql

        validation = self._sql_validator.validate(sql)
        if not validation.is_valid:
            reason = "; ".join(validation.violations) or "SQL is not allowed."
            raise ReadOnlySQLViolationError(
                reason,
                sql=sql,
                reason=reason,
            )
        return validation.normalized_sql or sql
