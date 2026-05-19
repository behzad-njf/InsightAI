"""Unit tests for GenerateAnswerUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerRequest,
)
from insightai.domain.models.database import QueryColumn, QueryExecutionOptions, QueryResult
from insightai.domain.models.llm import LLMProviderKind, TokenUsage
from insightai.domain.models.query_execution import RunQueryResult, RunQuerySQLSource


@pytest.fixture
def query_result() -> QueryResult:
    return QueryResult(
        columns=[QueryColumn(name="n")],
        rows=[],
        row_count=0,
    )


@pytest.mark.asyncio
async def test_execute_with_query_result(query_result: QueryResult) -> None:
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(
        return_value=AnswerGenerationResult(
            answer="No rows were returned.",
            row_count=0,
            truncation_noted=False,
            usage=TokenUsage(total_tokens=10),
            provider=LLMProviderKind.GROQ,
        ),
    )
    use_case = GenerateAnswerUseCase(mock_generator)
    result = await use_case.execute(
        GenerateAnswerRequest(
            question="How many users?",
            sql="SELECT COUNT(*) FROM accounts_user",
            query_result=query_result,
        ),
    )

    assert result.question == "How many users?"
    assert result.answer.answer.startswith("No rows")
    assert result.query_result.row_count == 0
    mock_generator.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_from_run_query_result(query_result: QueryResult) -> None:
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(
        return_value=AnswerGenerationResult(
            answer="Done.",
            row_count=0,
            truncation_noted=False,
        ),
    )
    use_case = GenerateAnswerUseCase(mock_generator)
    run = RunQueryResult(
        sql="SELECT COUNT(*) FROM accounts_user",
        source=RunQuerySQLSource.RAW,
        query_result=query_result,
        question="Count users?",
        execution_options=QueryExecutionOptions(),
    )
    result = await use_case.execute(
        GenerateAnswerRequest(
            question="Count users?",
            run_query_result=run,
        ),
    )

    assert result.sql == "SELECT COUNT(*) FROM accounts_user"
    assert result.answer.answer == "Done."


def test_generate_answer_request_rejects_both_sources(query_result: QueryResult) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        GenerateAnswerRequest(
            question="Q",
            sql="SELECT 1",
            query_result=query_result,
            run_query_result=RunQueryResult(
                sql="SELECT 1",
                source=RunQuerySQLSource.RAW,
                query_result=query_result,
                execution_options=QueryExecutionOptions(),
            ),
        )
