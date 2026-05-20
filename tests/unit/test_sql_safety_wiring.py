"""Phase 5.2 — composite SQL validator wiring across app paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.exceptions import ReadOnlySQLViolationError, SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.query_execution import RunQueryRequest
from insightai.infrastructure.ai.factory import build_ai_components
from insightai.infrastructure.ai.sql_postprocessor import postprocess_generated_sql
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import (
    CompositeSQLValidator,
    create_sql_safety_validator,
)
from tests.conftest import make_settings


def test_bootstrap_validator_is_composite() -> None:
    settings = make_settings(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
    )
    components = build_database_components(settings)
    assert isinstance(components.validator, CompositeSQLValidator)
    assert components.validator.database_kind == DatabaseKind.SQLITE
    components.engine.dispose()


def test_build_ai_components_uses_shared_validator() -> None:
    settings = make_settings(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
        groq_api_key="test-groq-key",
    )
    db = build_database_components(settings)
    ai = build_ai_components(settings, sql_validator=db.validator)
    generator = ai.sql_generator
    assert isinstance(generator._sql_validator, CompositeSQLValidator)
    assert generator._sql_validator is db.validator
    db.engine.dispose()


def test_postprocessor_default_uses_composite() -> None:
    settings = make_settings(database_kind=DatabaseKind.SQLITE)
    result = postprocess_generated_sql(
        "SELECT 'DELETE' AS tag FROM accounts_user",
        database_kind=DatabaseKind.SQLITE,
        settings=settings,
    )
    assert "DELETE" in result.sql


def test_postprocessor_sqlite_rejects_top_without_mssql_dialect() -> None:
    settings = make_settings(database_kind=DatabaseKind.SQLITE)
    with pytest.raises(SQLGenerationRejectedError):
        postprocess_generated_sql(
            "SELECT TOP 5 id FROM accounts_user",
            database_kind=DatabaseKind.SQLITE,
            settings=settings,
        )


@pytest.mark.asyncio
async def test_run_query_rejects_delete_before_executor() -> None:
    executor = MagicMock(spec=ReadOnlyQueryExecutor)
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    use_case = RunQueryUseCase(executor, sql_validator=validator)

    with pytest.raises(ReadOnlySQLViolationError):
        await use_case.execute(RunQueryRequest.from_sql("DELETE FROM accounts_user"))

    executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_query_with_shared_bootstrap_validator() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO accounts_user (id, email) VALUES (1, 'a@test.com')"))

    settings = make_settings(database_kind=DatabaseKind.SQLITE)
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE, settings=settings)
    executor = ReadOnlyQueryExecutor(engine, validator, kind=DatabaseKind.SQLITE)
    use_case = RunQueryUseCase(
        executor,
        settings,
        sql_validator=validator,
        execution_defaults=settings.get_query_execution_options(),
    )

    result = await use_case.execute(
        RunQueryRequest.from_sql("SELECT email FROM accounts_user"),
    )
    assert result.query_result.row_count == 1
    assert result.sql.upper().startswith("SELECT")
