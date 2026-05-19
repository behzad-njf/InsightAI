"""Phase 5.4 — end-to-end SQLite: validate → execute with real bootstrap stack."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import DBAPIError

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.exceptions import (
    DatabaseQueryTimeoutError,
    ReadOnlySQLViolationError,
)
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.domain.models.query_execution import RunQueryRequest, RunQuerySQLSource
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    SQLGenerationConfidence,
    SQLGenerationResult,
)
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.prompts.loader import load_sql_generation_prompts
from insightai.infrastructure.schema.loader import (
    clear_schema_repository_cache,
    get_schema_repository,
)
from insightai.infrastructure.security.composite_sql_validator import CompositeSQLValidator
from tests.conftest import make_settings
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION
from tests.fixtures.sqlite_e2e_schema import (
    CLASSROOM_SQL_SQLITE,
    CLASSROOM_SQLITE_LLM_JSON,
    seed_classroom_sqlite,
)

pytestmark = pytest.mark.integration

SQLITE_MEMORY_URL = "sqlite:///:memory:"


@pytest.fixture
def e2e_settings() -> Generator:
    yield make_settings(
        groq_api_key="gsk-e2e-test",
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url=SQLITE_MEMORY_URL,
        sql_max_rows=100,
        sql_query_timeout_seconds=30,
        sql_enforce_readonly=True,
    )


@pytest.fixture
def e2e_stack(e2e_settings) -> Generator:
    """Real bootstrap components + seeded SQLite + run-query use case."""
    components = build_database_components(e2e_settings)
    seed_classroom_sqlite(components.engine)

    run_query = RunQueryUseCase(
        components.executor,
        e2e_settings,
        sql_validator=components.validator,
        execution_defaults=components.execution_options,
    )
    yield e2e_settings, components, run_query
    components.engine.dispose()


def test_e2e_bootstrap_uses_readonly_sqlite_config(e2e_stack) -> None:
    _settings, components, _run_query = e2e_stack
    assert components.config.kind == DatabaseKind.SQLITE
    assert components.config.readonly is True
    assert isinstance(components.validator, CompositeSQLValidator)
    assert components.execution_options.max_rows == 100


def test_e2e_raw_sql_returns_rows(e2e_stack) -> None:
    _settings, _components, run_query = e2e_stack
    result = run_query.execute(
        RunQueryRequest.from_sql("SELECT id, email FROM accounts_user ORDER BY id"),
    )
    assert result.source == RunQuerySQLSource.RAW
    assert result.query_result.row_count == 3
    assert result.query_result.rows[0]["email"] == "child1@test.com"
    assert result.execution_options.max_rows == 100


def test_e2e_generated_sql_classroom_aggregate(e2e_stack) -> None:
    _settings, _components, run_query = e2e_stack
    generated = SQLGenerationResult(
        sql=CLASSROOM_SQL_SQLITE,
        explanation="Children per classroom.",
        confidence=SQLGenerationConfidence.HIGH,
        tables_used=["school_classroom", "school_classroomchild", "accounts_user"],
    )
    result = run_query.execute(RunQueryRequest.from_generation(generated))
    assert result.source == RunQuerySQLSource.GENERATED
    assert result.query_result.row_count == 2
    by_id = {row["classroom_id"]: row["child_count"] for row in result.query_result.rows}
    assert by_id[10] == 2
    assert by_id[20] == 1


def test_e2e_invalid_sql_never_executes(e2e_stack) -> None:
    _settings, components, run_query = e2e_stack
    execute_called = False
    real_execute = components.executor.execute

    def tracking_execute(*args, **kwargs):
        nonlocal execute_called
        execute_called = True
        return real_execute(*args, **kwargs)

    components.executor.execute = tracking_execute  # type: ignore[method-assign]
    with pytest.raises(ReadOnlySQLViolationError):
        run_query.execute(RunQueryRequest.from_sql("DELETE FROM accounts_user"))
    assert execute_called is False


def test_e2e_truncation_respects_sql_max_rows(e2e_settings) -> None:
    settings = e2e_settings.model_copy(update={"sql_max_rows": 1})
    components = build_database_components(settings)
    seed_classroom_sqlite(components.engine)
    try:
        run_query = RunQueryUseCase(
            components.executor,
            settings,
            sql_validator=components.validator,
            execution_defaults=components.execution_options,
        )
        result = run_query.execute(
            RunQueryRequest.from_sql("SELECT id FROM accounts_user ORDER BY id"),
        )
        assert result.query_result.row_count == 1
        assert result.query_result.truncated is True
        assert result.execution_options.max_rows == 1
    finally:
        components.engine.dispose()


@pytest.mark.asyncio
async def test_e2e_generate_sql_then_execute_sqlite(e2e_stack) -> None:
    """Full pipeline: mocked LLM SQL generation → run query on seeded SQLite."""
    settings, components, run_query = e2e_stack
    clear_schema_repository_cache()

    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=CLASSROOM_SQLITE_LLM_JSON,
            model="test-model",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            finish_reason="stop",
        )
    )
    sql_generator = LLMSQLGenerator(
        mock_framework,
        settings,
        prompt_bundle=load_sql_generation_prompts(settings),
        sql_validator=components.validator,
    )
    generate_sql = GenerateSQLUseCase(
        BuildSchemaContextUseCase(get_schema_repository()),
        sql_generator,
        settings,
    )

    with patch("insightai.api.deps.get_schema_repository") as mock_get_repo:
        mock_get_repo.side_effect = get_schema_repository
        gen_result = await generate_sql.execute(
            GenerateSQLRequest(
                question=CLASSROOM_QUESTION,
                database_kind=DatabaseKind.SQLITE,
                max_context_tables=12,
            ),
        )

    assert gen_result.sql.has_sql
    run_result = run_query.execute(RunQueryRequest.from_generate_sql(gen_result))
    assert run_result.query_result.row_count == 2
    assert run_result.question == CLASSROOM_QUESTION
    assert "classroom_id" in run_result.query_result.rows[0]


def test_e2e_query_timeout_raises_database_query_timeout_error(e2e_stack) -> None:
    """DB timeout from driver → DatabaseQueryTimeoutError through RunQueryUseCase."""
    _settings, components, run_query = e2e_stack
    orig = Exception("Query timeout expired")
    dbapi_exc = DBAPIError("SELECT ...", {}, orig)

    with patch.object(components.executor._engine, "connect") as mock_connect:
        connection = MagicMock()
        mock_connect.return_value.__enter__.return_value = connection
        connection.execution_options.return_value.execute.side_effect = dbapi_exc

        with pytest.raises(DatabaseQueryTimeoutError) as exc_info:
            run_query.execute(RunQueryRequest.from_sql("SELECT 1"))

    assert "30" in str(exc_info.value)


def test_e2e_string_delete_in_sql_passes_validation_and_runs(e2e_stack) -> None:
    """AST layer must allow keywords inside string literals (Phase 4 regression)."""
    _settings, _components, run_query = e2e_stack
    result = run_query.execute(
        RunQueryRequest.from_sql(
            "SELECT 'DELETE' AS tag, id FROM accounts_user ORDER BY id LIMIT 1",
        ),
    )
    assert result.query_result.row_count == 1
