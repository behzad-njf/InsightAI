"""Unit tests for AskUseCase (Phase 6.4 pipeline)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.ask import AskUseCase
from insightai.domain.exceptions import SQLGenerationError
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerResult,
    GenerateAnswerStreamChunk,
)
from insightai.domain.models.ask import AskRequest, AskStreamPhase
from insightai.domain.models.database import (
    QueryColumn,
    QueryExecutionOptions,
    QueryResult,
)
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.domain.models.query_execution import RunQueryResult, RunQuerySQLSource
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql_generation import (
    GenerateSQLResult,
    SQLGenerationConfidence,
    SQLGenerationResult,
)


def _sql_result(*, has_sql: bool = True) -> GenerateSQLResult:
    return GenerateSQLResult(
        question="How many children per classroom?",
        schema_context=SchemaContextResult(
            question="How many children per classroom?",
            tables=[],
            join_patterns=[],
            context_markdown="### school_classroom",
            table_names=["school_classroom"],
        ),
        sql=SQLGenerationResult(
            sql="SELECT 1" if has_sql else "",
            explanation="test" if has_sql else "Schema insufficient.",
            confidence=SQLGenerationConfidence.HIGH if has_sql else SQLGenerationConfidence.LOW,
        ),
    )


def _run_result() -> RunQueryResult:
    return RunQueryResult(
        sql="SELECT 1",
        source=RunQuerySQLSource.GENERATED,
        query_result=QueryResult(
            columns=[QueryColumn(name="n")],
            rows=[{"n": 1}],
            row_count=1,
            executed_at=datetime.now(UTC),
        ),
        question="How many children per classroom?",
        execution_options=QueryExecutionOptions(),
    )


def _answer_result() -> GenerateAnswerResult:
    return GenerateAnswerResult(
        question="How many children per classroom?",
        sql="SELECT 1",
        query_result=_run_result().query_result,
        answer=AnswerGenerationResult(
            answer="One row returned.",
            row_count=1,
            truncation_noted=False,
        ),
    )


@pytest.fixture
def ask_use_case() -> AskUseCase:
    generate_sql = MagicMock()
    generate_sql.execute = AsyncMock(return_value=_sql_result())
    run_query = MagicMock()
    run_query.execute = AsyncMock(return_value=_run_result())
    generate_answer = MagicMock()
    generate_answer.execute = AsyncMock(return_value=_answer_result())
    return AskUseCase(generate_sql, run_query, generate_answer)


@pytest.mark.asyncio
async def test_ask_runs_sql_execute_answer_in_order(ask_use_case: AskUseCase) -> None:
    result = await ask_use_case.execute(
        AskRequest(question="How many children per classroom?"),
    )

    assert result.question == "How many children per classroom?"
    assert result.sql.sql.has_sql
    assert result.execution.query_result.row_count == 1
    assert "One row" in result.answer.answer.answer
    assert result.timings.total_ms >= 0
    assert result.timings.sql_generation_ms >= 0
    assert result.timings.query_execution_ms >= 0
    assert result.timings.answer_generation_ms >= 0
    assert result.explainability is not None
    assert result.explainability.route == QueryRouteKind.SQL

    ask_use_case._generate_sql.execute.assert_awaited_once()  # type: ignore[attr-defined]
    ask_use_case._run_query.execute.assert_awaited_once()  # type: ignore[attr-defined]
    ask_use_case._generate_answer.execute.assert_awaited_once()  # type: ignore[attr-defined]


def _mock_execute_stream(result: GenerateAnswerResult):
    async def stream(_request):  # noqa: ANN001
        yield GenerateAnswerStreamChunk.token("One ")
        yield GenerateAnswerStreamChunk.token("row.")
        yield GenerateAnswerStreamChunk.done(result)

    return stream


@pytest.mark.asyncio
async def test_ask_execute_stream_emits_status_tokens_and_done(
    ask_use_case: AskUseCase,
) -> None:
    answer = _answer_result()
    ask_use_case._generate_answer.execute_stream = _mock_execute_stream(answer)  # type: ignore[method-assign]

    events = [
        event
        async for event in ask_use_case.execute_stream(
            AskRequest(question="How many children per classroom?"),
        )
    ]

    assert [e.kind for e in events] == [
        "status",
        "status",
        "status",
        "status",
        "status",
        "token",
        "token",
        "done",
    ]
    assert events[0].phase == AskStreamPhase.GENERATING_SQL
    assert events[1].phase == AskStreamPhase.APPLYING_GOVERNANCE
    assert events[2].phase == AskStreamPhase.VALIDATING_SQL
    assert events[3].phase == AskStreamPhase.EXECUTING_QUERY
    assert events[4].phase == AskStreamPhase.GENERATING_ANSWER
    assert events[5].text == "One "
    assert events[6].text == "row."
    assert events[7].result is not None
    assert events[7].result.answer.answer.answer == "One row returned."
    assert events[7].result.timings.total_ms >= 0
    assert events[7].result.explainability is not None


@pytest.mark.asyncio
async def test_ask_execute_stream_error_when_sql_empty(ask_use_case: AskUseCase) -> None:
    ask_use_case._generate_sql.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_sql_result(has_sql=False),
    )

    events = [
        event
        async for event in ask_use_case.execute_stream(
            AskRequest(question="Unknown metric?"),
        )
    ]

    assert events[0].kind == "status"
    assert events[-1].kind == "error"
    assert events[-1].error_code == "sql_generation_error"
    ask_use_case._run_query.execute.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_ask_raises_when_sql_empty(ask_use_case: AskUseCase) -> None:
    ask_use_case._generate_sql.execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_sql_result(has_sql=False),
    )

    with pytest.raises(SQLGenerationError, match="Cannot execute"):
        await ask_use_case.execute(AskRequest(question="Unknown metric?"))

    ask_use_case._run_query.execute.assert_not_called()  # type: ignore[attr-defined]
    ask_use_case._generate_answer.execute.assert_not_awaited()  # type: ignore[attr-defined]
