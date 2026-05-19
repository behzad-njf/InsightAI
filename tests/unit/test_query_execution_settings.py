"""Phase 5.3 — settings-driven query execution limits."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions
from insightai.domain.models.query_execution import RunQueryRequest
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from tests.conftest import make_settings


def test_settings_exposes_query_execution_options() -> None:
    settings = make_settings(
        sql_max_rows=42,
        sql_query_timeout_seconds=17,
        sql_enforce_readonly=False,
    )
    opts = settings.get_query_execution_options()
    assert opts.max_rows == 42
    assert opts.timeout_seconds == 17
    assert opts.enforce_readonly is False


def test_bootstrap_execution_options_from_settings() -> None:
    settings = make_settings(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
        sql_max_rows=3,
        sql_query_timeout_seconds=45,
    )
    components = build_database_components(settings)
    assert components.config.readonly is True
    assert components.execution_options.max_rows == 3
    assert components.execution_options.timeout_seconds == 45
    assert components.executor.default_options.max_rows == 3
    components.engine.dispose()


def test_executor_applies_settings_max_rows_without_explicit_options() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        for i in range(1, 6):
            conn.execute(
                text("INSERT INTO accounts_user (id, email) VALUES (:id, :email)"),
                {"id": i, "email": f"u{i}@test.com"},
            )

    defaults = QueryExecutionOptions(max_rows=2, timeout_seconds=30)
    executor = ReadOnlyQueryExecutor(
        engine,
        create_sql_safety_validator(kind=DatabaseKind.SQLITE),
        kind=DatabaseKind.SQLITE,
        default_options=defaults,
    )
    result = executor.execute("SELECT id FROM accounts_user ORDER BY id")
    assert result.row_count == 2
    assert result.truncated is True


def test_run_query_use_case_applies_settings_defaults() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        for i in range(1, 4):
            conn.execute(
                text("INSERT INTO accounts_user (id, email) VALUES (:id, :email)"),
                {"id": i, "email": f"u{i}@test.com"},
            )

    settings = make_settings(sql_max_rows=1, sql_query_timeout_seconds=99)
    defaults = settings.get_query_execution_options()
    executor = ReadOnlyQueryExecutor(
        engine,
        create_sql_safety_validator(kind=DatabaseKind.SQLITE, settings=settings),
        kind=DatabaseKind.SQLITE,
        default_options=defaults,
    )
    use_case = RunQueryUseCase(
        executor,
        settings,
        sql_validator=create_sql_safety_validator(kind=DatabaseKind.SQLITE, settings=settings),
        execution_defaults=defaults,
    )
    result = use_case.execute(
        RunQueryRequest.from_sql("SELECT id FROM accounts_user ORDER BY id"),
    )
    assert result.execution_options.max_rows == 1
    assert result.execution_options.timeout_seconds == 99
    assert result.query_result.truncated is True
    assert result.query_result.row_count == 1


def test_run_query_request_override_beats_settings_defaults() -> None:
    settings = make_settings(sql_max_rows=1000)
    defaults = settings.get_query_execution_options()
    merged = RunQueryRequest.from_sql(
        "SELECT 1",
        max_rows=5,
        timeout_seconds=10,
    ).to_execution_options(defaults)
    assert merged.max_rows == 5
    assert merged.timeout_seconds == 10
