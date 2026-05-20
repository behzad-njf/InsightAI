"""Execute validated read-only SQL (Phase 5.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.exceptions import (
    DatabaseError,
    DatabaseQueryError,
    ReadOnlySQLViolationError,
)
from insightai.domain.models.database import QueryExecutionOptions  # noqa: TC001
from insightai.domain.models.query_execution import RunQueryRequest, RunQueryResult
from insightai.infrastructure.cache.query_cache import (
    get_cached_run_query_result,
    query_result_cache_key,
    set_cached_run_query_result,
)
from insightai.infrastructure.observability.tracing import set_span_attributes, start_span

if TYPE_CHECKING:
    from insightai.domain.ports.cache import ICache
    from insightai.domain.ports.database import IReadOnlyQueryExecutor
    from insightai.domain.ports.sql_safety import ISQLSafetyValidator
    from insightai.infrastructure.config.settings import Settings


class RunQueryUseCase:
    """
    Validate and execute read-only SQL via ``IReadOnlyQueryExecutor``.

    Accepts raw SQL or Phase 3 generation output (``SQLGenerationResult`` /
    ``GenerateSQLResult``). Invalid SQL is rejected by the composite validator
    before any database round-trip (Phase 4). Successful results may be cached
    (Phase 9.3); failures and unsafe SQL are never cached.
    """

    def __init__(
        self,
        executor: IReadOnlyQueryExecutor,
        settings: Settings | None = None,
        *,
        sql_validator: ISQLSafetyValidator | None = None,
        execution_defaults: QueryExecutionOptions | None = None,
        cache: ICache | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._executor = executor
        self._settings = settings or get_settings()
        self._sql_validator = sql_validator
        self._execution_defaults = (
            execution_defaults or self._settings.get_query_execution_options()
        )
        self._cache = cache

    async def execute(self, request: RunQueryRequest) -> RunQueryResult:
        try:
            sql = request.resolve_sql()
        except ValueError as exc:
            raise DatabaseQueryError(str(exc)) from exc

        options = request.to_execution_options(self._execution_defaults)

        try:
            sql_to_run = self._validate_before_execute(sql, enforce=options.enforce_readonly)
        except ReadOnlySQLViolationError:
            raise

        cache_active = self._query_cache_active()
        key: str | None = None
        if cache_active and self._cache is not None:
            scope = self._resolve_cache_scope(request.cache_scope)
            key = query_result_cache_key(
                sql_to_run,
                options,
                self._settings.database_kind,
                cache_scope=scope,
            )
            cached = await get_cached_run_query_result(self._cache, key)
            if cached is not None:
                with start_span(
                    "insightai.db.query",
                    attributes={"insightai.query.cache_hit": True},
                ):
                    set_span_attributes({"db.system": self._settings.database_kind.value})
                return cached

        with start_span(
            "insightai.db.query",
            attributes={"insightai.query.cache_hit": False},
        ):
            try:
                query_result = self._executor.execute(sql_to_run, options=options)
            except DatabaseError:
                raise
            except Exception as exc:
                raise DatabaseQueryError(str(exc)) from exc

        question: str | None = None
        if request.generate_result is not None:
            question = request.generate_result.question
        generation = request.resolved_generation()

        result = RunQueryResult(
            sql=sql_to_run,
            source=request.sql_source(),
            query_result=query_result,
            question=question,
            generation=generation,
            execution_options=options,
        )

        if cache_active and self._cache is not None and key is not None:
            ttl = self._settings.cache_query_results_ttl_seconds
            if ttl is None:
                ttl = self._settings.cache_default_ttl_seconds
            await set_cached_run_query_result(
                self._cache,
                key,
                result,
                ttl_seconds=ttl,
            )

        return result

    def _query_cache_active(self) -> bool:
        return self._settings.cache_enabled and self._settings.cache_query_results_enabled

    def _resolve_cache_scope(self, cache_scope: str | None) -> str | None:
        if not self._settings.cache_query_results_scope_user:
            return None
        return cache_scope

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
