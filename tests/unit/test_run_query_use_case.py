"""Unit tests for RunQueryUseCase (Phase 5.1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.exceptions import ReadOnlySQLViolationError
from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions
from insightai.domain.models.query_execution import RunQueryRequest, RunQuerySQLSource
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql_generation import (
    GenerateSQLResult,
    SQLGenerationConfidence,
    SQLGenerationResult,
)
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from tests.conftest import make_settings


@pytest.fixture
def run_query() -> RunQueryUseCase:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (2, 'b@test.com')"))
    settings = make_settings(sql_max_rows=1000)
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


def test_execute_raw_sql(run_query: RunQueryUseCase) -> None:
    result = run_query.execute(
        RunQueryRequest.from_sql(
            "SELECT id, email FROM accounts_user ORDER BY id",
        ),
    )
    assert result.source == RunQuerySQLSource.RAW
    assert result.question is None
    assert result.generation is None
    assert result.query_result.row_count == 2
    assert result.sql.upper().startswith("SELECT")


def test_execute_from_sql_generation_result(run_query: RunQueryUseCase) -> None:
    generated = SQLGenerationResult(
        sql="SELECT email FROM accounts_user WHERE id = 1",
        explanation="One user email.",
        confidence=SQLGenerationConfidence.HIGH,
    )
    result = run_query.execute(RunQueryRequest.from_generation(generated))
    assert result.source == RunQuerySQLSource.GENERATED
    assert result.generation is generated
    assert result.query_result.row_count == 1
    assert result.query_result.rows[0]["email"] == "a@test.com"


def test_execute_from_generate_sql_result(run_query: RunQueryUseCase) -> None:
    generated = SQLGenerationResult(
        sql="SELECT COUNT(*) AS n FROM accounts_user",
        explanation="Count users.",
        confidence=SQLGenerationConfidence.MEDIUM,
    )
    gen_result = GenerateSQLResult(
        question="How many users?",
        schema_context=SchemaContextResult(
            question="How many users?",
            tables=[],
            join_patterns=[],
            context_markdown="## schema",
            table_names=[],
        ),
        sql=generated,
    )
    result = run_query.execute(RunQueryRequest.from_generate_sql(gen_result))
    assert result.source == RunQuerySQLSource.GENERATED
    assert result.question == "How many users?"
    assert result.query_result.rows[0]["n"] == 2


def test_rejects_delete_before_db(run_query: RunQueryUseCase) -> None:
    with pytest.raises(ReadOnlySQLViolationError):
        run_query.execute(RunQueryRequest.from_sql("DELETE FROM accounts_user"))


def test_rejects_empty_raw_sql() -> None:
    with pytest.raises(ValueError, match="Provide one of"):
        RunQueryRequest(sql="   ")


def test_rejects_empty_generated_sql() -> None:
    generated = SQLGenerationResult(
        sql="",
        explanation="No SQL.",
        confidence=SQLGenerationConfidence.LOW,
    )
    with pytest.raises(ValueError, match="Provide one of"):
        RunQueryRequest.from_generation(generated)


def test_rejects_multiple_sql_sources() -> None:
    with pytest.raises(ValueError, match="only one"):
        RunQueryRequest(
            sql="SELECT 1",
            generated_sql=SQLGenerationResult(
                sql="SELECT 2",
                explanation="x",
                confidence=SQLGenerationConfidence.HIGH,
            ),
        )


def test_respects_max_rows_override(run_query: RunQueryUseCase) -> None:
    result = run_query.execute(
        RunQueryRequest.from_sql(
            "SELECT id FROM accounts_user ORDER BY id",
            max_rows=1,
        ),
    )
    assert result.query_result.row_count == 1
    assert result.query_result.truncated is True


def test_request_to_execution_options_merges_defaults() -> None:
    defaults = QueryExecutionOptions(max_rows=1000, timeout_seconds=30)
    merged = RunQueryRequest.from_sql("SELECT 1", max_rows=5).to_execution_options(defaults)
    assert merged.max_rows == 5
    assert merged.timeout_seconds == 30
