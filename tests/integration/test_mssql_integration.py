"""Phase 5.5 — optional MSSQL integration (env-gated, requires pyodbc + ODBC)."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.exceptions import ReadOnlySQLViolationError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.query_execution import RunQueryRequest
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.security.composite_sql_validator import CompositeSQLValidator
from tests.conftest import make_settings
from tests.integration.mssql_env import (
    MSSQL_INTEGRATION_URL_ENV,
    mssql_integration_url,
    pyodbc_available,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.mssql,
    pytest.mark.skipif(
        mssql_integration_url() is None,
        reason=f"Set {MSSQL_INTEGRATION_URL_ENV} to run MSSQL integration tests",
    ),
    pytest.mark.skipif(
        not pyodbc_available(),
        reason="pyodbc not installed (pip install -e '.[mssql]')",
    ),
]


@pytest.fixture
def mssql_settings():
    url = mssql_integration_url()
    assert url is not None
    return make_settings(
        groq_api_key="gsk-mssql-integration",
        database_kind=DatabaseKind.MSSQL,
        database_readonly_url=url,
        sql_max_rows=100,
        sql_query_timeout_seconds=30,
        sql_enforce_readonly=True,
    )


@pytest.fixture
def mssql_stack(mssql_settings) -> Generator:
    """Real bootstrap against external MSSQL (readonly URL from env)."""
    components = build_database_components(mssql_settings)
    run_query = RunQueryUseCase(
        components.executor,
        mssql_settings,
        sql_validator=components.validator,
        execution_defaults=components.execution_options,
    )
    yield mssql_settings, components, run_query
    components.engine.dispose()


def test_mssql_bootstrap_uses_readonly_mssql_config(mssql_stack) -> None:
    _settings, components, _run_query = mssql_stack
    assert components.config.kind == DatabaseKind.MSSQL
    assert components.config.readonly is True
    assert isinstance(components.validator, CompositeSQLValidator)


def test_mssql_health_check(mssql_stack) -> None:
    _settings, components, _run_query = mssql_stack
    status = components.health_check.check()
    assert status.healthy is True
    assert status.kind == DatabaseKind.MSSQL


@pytest.mark.asyncio
async def test_mssql_run_query_select_one(mssql_stack) -> None:
    _settings, _components, run_query = mssql_stack
    result = await run_query.execute(RunQueryRequest.from_sql("SELECT 1 AS n"))
    assert result.query_result.row_count == 1
    assert result.query_result.rows[0]["n"] == 1
    assert result.execution_options.max_rows == 100


@pytest.mark.asyncio
async def test_mssql_invalid_sql_never_executes(mssql_stack) -> None:
    _settings, components, run_query = mssql_stack
    execute_called = False
    real_execute = components.executor.execute

    def tracking_execute(*args, **kwargs):
        nonlocal execute_called
        execute_called = True
        return real_execute(*args, **kwargs)

    components.executor.execute = tracking_execute  # type: ignore[method-assign]
    with pytest.raises(ReadOnlySQLViolationError):
        await run_query.execute(RunQueryRequest.from_sql("DELETE FROM accounts_user"))
    assert execute_called is False


def test_mssql_validator_accepts_with_cte_and_top(mssql_stack) -> None:
    _settings, components, _run_query = mssql_stack
    sql = "WITH cte AS (SELECT 1 AS n) SELECT TOP 5 n FROM cte"
    validation = components.validator.validate(sql)
    assert validation.is_valid
