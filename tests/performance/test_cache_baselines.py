"""
Cache performance baselines (Phase 9.4).

Compares cold vs warm latency for schema context and query result caches.
Uses simulated slow backends in most tests for stable CI; one optional slow test
hits the real ``database_schema.md`` parser path.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.query_execution import RunQueryRequest
from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.infrastructure.cache.memory_cache import MemoryCache
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.schema.bootstrap import build_schema_components
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from tests.conftest import make_settings
from tests.performance.conftest import (
    MAX_CACHE_HIT_MS,
    MIN_CACHE_SPEEDUP_RATIO,
    SIMULATED_COLD_LATENCY_S,
)

T = TypeVar("T")

pytestmark = [pytest.mark.performance, pytest.mark.slow]


async def _measure_ms(awaitable: Callable[[], Awaitable[T]]) -> tuple[T, float]:
    started = time.perf_counter()
    result = await awaitable()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms


def _slow_schema_result(request: SchemaContextRequest) -> SchemaContextResult:
    time.sleep(SIMULATED_COLD_LATENCY_S)
    return SchemaContextResult(
        question=request.question,
        tables=[],
        join_patterns=[],
        context_markdown="### accounts_user",
        table_names=["accounts_user"],
    )


@pytest.mark.asyncio
async def test_schema_context_cache_faster_than_cold_path(schema_path: Path) -> None:
    settings = make_settings(cache_enabled=True, cache_schema_context_enabled=True)
    cache = MemoryCache(key_prefix="perf:schema:", default_ttl_seconds=300)
    mock_repository = MagicMock()
    mock_repository.build_context.side_effect = _slow_schema_result

    use_case = BuildSchemaContextUseCase(
        mock_repository,
        cache=cache,
        settings=settings,
        schema_path=schema_path,
    )
    request = SchemaContextRequest(question="children in a classroom", max_tables=12)

    _cold, cold_ms = await _measure_ms(lambda: use_case.execute(request))
    _warm, warm_ms = await _measure_ms(lambda: use_case.execute(request))

    assert mock_repository.build_context.call_count == 1
    assert warm_ms < cold_ms
    assert cold_ms / warm_ms >= MIN_CACHE_SPEEDUP_RATIO
    assert warm_ms <= MAX_CACHE_HIT_MS


@pytest.mark.asyncio
async def test_query_result_cache_faster_than_cold_path() -> None:
    settings = make_settings(
        cache_enabled=True,
        cache_query_results_enabled=True,
        database_kind=DatabaseKind.SQLITE,
    )
    cache = MemoryCache(key_prefix="perf:query:", default_ttl_seconds=120)

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')"))
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE, settings=settings)
    defaults = settings.get_query_execution_options()
    real_executor = ReadOnlyQueryExecutor(
        engine,
        validator,
        kind=DatabaseKind.SQLITE,
        default_options=defaults,
    )

    def slow_execute(sql: str, *, options: object) -> object:
        time.sleep(SIMULATED_COLD_LATENCY_S)
        return real_executor.execute(sql, options=options)  # type: ignore[arg-type]

    mock_executor = MagicMock()
    mock_executor.execute.side_effect = slow_execute

    use_case = RunQueryUseCase(
        mock_executor,
        settings,
        sql_validator=validator,
        execution_defaults=defaults,
        cache=cache,
    )
    request = RunQueryRequest.from_sql("SELECT email FROM accounts_user")

    _cold, cold_ms = await _measure_ms(lambda: use_case.execute(request))
    _warm, warm_ms = await _measure_ms(lambda: use_case.execute(request))

    assert mock_executor.execute.call_count == 1
    assert warm_ms < cold_ms
    assert cold_ms / warm_ms >= MIN_CACHE_SPEEDUP_RATIO
    assert warm_ms <= MAX_CACHE_HIT_MS


@pytest.mark.asyncio
async def test_schema_context_without_cache_stays_slow(schema_path: Path) -> None:
    settings = make_settings(cache_enabled=False)
    mock_repository = MagicMock()
    mock_repository.build_context.side_effect = _slow_schema_result

    use_case = BuildSchemaContextUseCase(
        mock_repository,
        cache=MemoryCache(key_prefix="unused:", default_ttl_seconds=60),
        settings=settings,
        schema_path=schema_path,
    )
    request = SchemaContextRequest(question="repeat question", max_tables=8)

    _first, first_ms = await _measure_ms(lambda: use_case.execute(request))
    _second, second_ms = await _measure_ms(lambda: use_case.execute(request))

    assert mock_repository.build_context.call_count == 2
    assert first_ms >= SIMULATED_COLD_LATENCY_S * 1000 * 0.5
    assert second_ms >= SIMULATED_COLD_LATENCY_S * 1000 * 0.5


@pytest.fixture
def schema_path() -> Path:
    path = Path("schema/database_schema.md")
    if not path.is_file():
        pytest.skip("schema/database_schema.md not available")
    return path


@pytest.mark.asyncio
async def test_real_schema_context_cache_speedup(schema_path: Path) -> None:
    """
    Integration-style baseline: real schema markdown, in-memory cache.

    Skipped when the schema file is missing; tolerates machine variance via ratio only.
    """
    settings = make_settings(cache_enabled=True, cache_schema_context_enabled=True)
    components = build_schema_components(settings)
    cache = MemoryCache(key_prefix="perf:schema:real:", default_ttl_seconds=300)
    use_case = BuildSchemaContextUseCase(
        components.repository,
        cache=cache,
        settings=settings,
        schema_path=components.schema_path,
    )
    request = SchemaContextRequest(question="children in a classroom", max_tables=12)

    _cold, cold_ms = await _measure_ms(lambda: use_case.execute(request))
    _warm, warm_ms = await _measure_ms(lambda: use_case.execute(request))

    # Registry is already warm from ``build_schema_components``; cache still avoids
    # ``build_context`` on the second call. Allow small timing noise in CI.
    assert warm_ms <= cold_ms * 1.05 + 0.5
    assert warm_ms <= MAX_CACHE_HIT_MS
