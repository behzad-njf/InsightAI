"""Unit tests for Phase 9.3 query result caching."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.exceptions import DatabaseQueryError, ReadOnlySQLViolationError
from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions
from insightai.domain.models.query_execution import RunQueryRequest
from insightai.infrastructure.cache.memory_cache import MemoryCache
from insightai.infrastructure.cache.query_cache import query_result_cache_key
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from tests.conftest import make_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def sqlite_run_query() -> RunQueryUseCase:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')"))
    settings = make_settings(sql_max_rows=1000, database_kind=DatabaseKind.SQLITE)
    defaults = settings.get_query_execution_options()
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE, settings=settings)
    executor = ReadOnlyQueryExecutor(
        engine,
        validator,
        kind=DatabaseKind.SQLITE,
        default_options=defaults,
    )
    return RunQueryUseCase(
        executor,
        settings,
        sql_validator=validator,
        execution_defaults=defaults,
    )


async def test_query_cache_hit_skips_executor(sqlite_run_query: RunQueryUseCase) -> None:
    settings = make_settings(
        cache_enabled=True,
        cache_query_results_enabled=True,
        database_kind=DatabaseKind.SQLITE,
    )
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=120)
    mock_executor = MagicMock()
    mock_executor.execute.return_value = sqlite_run_query._executor.execute(  # noqa: SLF001
        "SELECT email FROM accounts_user",
        options=settings.get_query_execution_options(),
    )
    use_case = RunQueryUseCase(
        mock_executor,
        settings,
        sql_validator=sqlite_run_query._sql_validator,  # noqa: SLF001
        execution_defaults=settings.get_query_execution_options(),
        cache=cache,
    )
    request = RunQueryRequest.from_sql("SELECT email FROM accounts_user")

    first = await use_case.execute(request)
    second = await use_case.execute(request)

    assert first.query_result.row_count == second.query_result.row_count
    assert mock_executor.execute.call_count == 1


async def test_query_cache_keys_differ_by_user_scope(sqlite_run_query: RunQueryUseCase) -> None:
    settings = make_settings(
        cache_enabled=True,
        cache_query_results_enabled=True,
        cache_query_results_scope_user=True,
        database_kind=DatabaseKind.SQLITE,
    )
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=120)
    mock_executor = MagicMock()
    mock_executor.execute.return_value = sqlite_run_query._executor.execute(  # noqa: SLF001
        "SELECT email FROM accounts_user",
        options=settings.get_query_execution_options(),
    )
    use_case = RunQueryUseCase(
        mock_executor,
        settings,
        sql_validator=sqlite_run_query._sql_validator,  # noqa: SLF001
        execution_defaults=settings.get_query_execution_options(),
        cache=cache,
    )
    sql = "SELECT email FROM accounts_user"
    request = RunQueryRequest.from_sql(sql)

    await use_case.execute(request.model_copy(update={"cache_scope": "user-a"}))
    await use_case.execute(request.model_copy(update={"cache_scope": "user-b"}))

    assert mock_executor.execute.call_count == 2


async def test_unsafe_sql_not_cached(sqlite_run_query: RunQueryUseCase) -> None:
    settings = make_settings(cache_enabled=True, cache_query_results_enabled=True)
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=120)
    use_case = RunQueryUseCase(
        sqlite_run_query._executor,  # noqa: SLF001
        settings,
        sql_validator=sqlite_run_query._sql_validator,  # noqa: SLF001
        cache=cache,
    )

    with pytest.raises(ReadOnlySQLViolationError):
        await use_case.execute(RunQueryRequest.from_sql("DELETE FROM accounts_user"))

    assert await cache.get("any") is None


async def test_failed_query_not_cached(sqlite_run_query: RunQueryUseCase) -> None:
    settings = make_settings(cache_enabled=True, cache_query_results_enabled=True)
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=120)
    mock_executor = MagicMock()
    mock_executor.execute.side_effect = DatabaseQueryError("db down")
    use_case = RunQueryUseCase(
        mock_executor,
        settings,
        sql_validator=sqlite_run_query._sql_validator,  # noqa: SLF001
        cache=cache,
    )

    with pytest.raises(DatabaseQueryError):
        await use_case.execute(RunQueryRequest.from_sql("SELECT 1"))

    keys = list(cache._entries.keys())  # noqa: SLF001
    assert len(keys) == 0


def test_query_result_cache_key_includes_sql_and_scope() -> None:
    options = QueryExecutionOptions(max_rows=10, timeout_seconds=30)
    key_a = query_result_cache_key(
        "SELECT 1",
        options,
        DatabaseKind.SQLITE,
        cache_scope="alice",
    )
    key_b = query_result_cache_key(
        "SELECT 1",
        options,
        DatabaseKind.SQLITE,
        cache_scope="bob",
    )
    assert key_a != key_b
