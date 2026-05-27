"""Unit tests for ask pipeline dry_run and use_llm (Phase 11.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.ask import AskUseCase
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerResult,
)
from insightai.domain.models.ask import AskMode, AskRequest, AskStreamPhase
from insightai.domain.models.database import QueryColumn, QueryExecutionOptions, QueryResult
from insightai.domain.models.query_execution import RunQueryResult, RunQuerySQLSource
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql_generation import (
    GenerateSQLResult,
    SQLGenerationConfidence,
    SQLGenerationResult,
)


def _sql_result() -> GenerateSQLResult:
    return GenerateSQLResult(
        question="How many active users?",
        schema_context=SchemaContextResult(
            question="How many active users?",
            tables=[],
            join_patterns=[],
            context_markdown="### accounts_user",
            table_names=["accounts_user"],
        ),
        sql=SQLGenerationResult(
            sql="SELECT COUNT(*) FROM dbo.accounts_user WHERE is_active = 1",
            explanation="Count active users.",
            confidence=SQLGenerationConfidence.HIGH,
        ),
    )


def _answer_result(*, row_count: int = 0) -> GenerateAnswerResult:
    return GenerateAnswerResult(
        question="How many active users?",
        sql="SELECT COUNT(*) FROM dbo.accounts_user WHERE is_active = 1",
        query_result=QueryResult(columns=[], rows=[], row_count=row_count),
        answer=AnswerGenerationResult(
            answer="Dry-run summary.",
            row_count=row_count,
            truncation_noted=False,
        ),
    )


@pytest.fixture
def ask_use_case() -> AskUseCase:
    generate_sql = MagicMock()
    generate_sql.execute = AsyncMock(return_value=_sql_result())
    run_query = MagicMock()
    run_query.execute = AsyncMock()
    dry_run_sql = "SELECT COUNT(*) FROM dbo.accounts_user WHERE is_active = 1"
    run_query.validate_sql = AsyncMock(return_value=dry_run_sql)
    generate_answer = MagicMock()
    generate_answer.execute = AsyncMock(return_value=_answer_result())
    generate_answer.execute_stream = AsyncMock()
    return AskUseCase(generate_sql, run_query, generate_answer)


@pytest.mark.asyncio
async def test_dry_run_validates_without_execute(ask_use_case: AskUseCase) -> None:
    result = await ask_use_case.execute(
        AskRequest(question="How many active users?", mode=AskMode.DRY_RUN),
    )

    ask_use_case._run_query.execute.assert_not_awaited()  # type: ignore[attr-defined]
    assert result.dry_run is True
    assert result.execution.query_result.row_count == 0


@pytest.mark.asyncio
async def test_execute_mode_calls_run_query(ask_use_case: AskUseCase) -> None:
    run_result = RunQueryResult(
        sql="SELECT 1",
        source=RunQuerySQLSource.GENERATED,
        query_result=QueryResult(
            columns=[QueryColumn(name="n")],
            rows=[{"n": 1}],
            row_count=1,
            executed_at=datetime.now(UTC),
        ),
        execution_options=QueryExecutionOptions(),
    )
    ask_use_case._run_query.execute = AsyncMock(return_value=run_result)  # type: ignore[method-assign]
    ask_use_case._generate_answer.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_answer_result(),
    )

    result = await ask_use_case.execute(
        AskRequest(question="How many active users?", mode=AskMode.EXECUTE),
    )

    ask_use_case._run_query.execute.assert_awaited_once()  # type: ignore[attr-defined]
    ask_use_case._run_query.validate_sql.assert_not_awaited()  # type: ignore[attr-defined]
    assert result.dry_run is False
    assert result.execution.query_result.row_count == 1


@pytest.mark.asyncio
async def test_build_sql_request_forwards_use_llm(ask_use_case: AskUseCase) -> None:
    request = AskRequest(question="q", use_llm=False)
    sql_request = ask_use_case._build_sql_request(request)
    assert sql_request.use_llm is False


@pytest.mark.asyncio
async def test_dry_run_stream_emits_validating_phase(ask_use_case: AskUseCase) -> None:
    from insightai.domain.models.answer import GenerateAnswerStreamChunk

    async def _stream():
        yield GenerateAnswerStreamChunk.token("ok")
        yield GenerateAnswerStreamChunk.done(_answer_result())

    ask_use_case._generate_answer.execute_stream = _stream  # type: ignore[method-assign]

    phases: list[str] = []
    async for event in ask_use_case.execute_stream(
        AskRequest(question="How many active users?", mode=AskMode.DRY_RUN),
    ):
        if event.kind == "status" and event.phase is not None:
            phases.append(event.phase.value)

    assert AskStreamPhase.APPLYING_GOVERNANCE.value in phases
    assert AskStreamPhase.VALIDATING_SQL.value in phases
    assert AskStreamPhase.EXECUTING_QUERY.value not in phases
