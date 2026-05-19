"""Unit tests for GenerateSQLUseCase orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, TokenUsage
from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    SQLGenerationConfidence,
    SQLGenerationRequest,
    SQLGenerationResult,
)
from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_generate_sql_orchestrates_context_then_generation() -> None:
    settings = make_settings(groq_api_key="gsk-test", database_kind=DatabaseKind.MSSQL)

    schema_result = SchemaContextResult(
        question="List children in classrooms",
        tables=[],
        join_patterns=[],
        context_markdown="### school_classroomchild",
        table_names=["school_classroomchild", "accounts_user"],
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = schema_result

    sql_result = SQLGenerationResult(
        sql="SELECT TOP 10 id FROM school_classroomchild",
        explanation="Lists classroom children.",
        confidence=SQLGenerationConfidence.HIGH,
        tables_used=["school_classroomchild"],
        schema_table_names=["school_classroomchild", "accounts_user"],
        usage=TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        provider=LLMProviderKind.GROQ,
    )
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=sql_result)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
    )

    result = await use_case.execute(
        GenerateSQLRequest(
            question="List children in classrooms",
            max_context_tables=8,
        )
    )

    mock_repository.build_context.assert_called_once()
    ctx_call: SchemaContextRequest = mock_repository.build_context.call_args.args[0]
    assert ctx_call.question == "List children in classrooms"
    assert ctx_call.max_tables == 8

    mock_generator.generate.assert_awaited_once()
    gen_call: SQLGenerationRequest = mock_generator.generate.await_args.args[0]
    assert gen_call.schema_context == "### school_classroomchild"
    assert gen_call.database_kind == DatabaseKind.MSSQL

    assert result.schema_context.table_names == ["school_classroomchild", "accounts_user"]
    assert result.sql.has_sql is True
    assert "school_classroomchild" in result.sql.sql


@pytest.mark.asyncio
async def test_generate_sql_uses_database_kind_override() -> None:
    settings = make_settings(groq_api_key="gsk-test", database_kind=DatabaseKind.MSSQL)
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = SchemaContextResult(
        question="q",
        tables=[],
        join_patterns=[],
        context_markdown="ctx",
        table_names=[],
    )
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(
        return_value=SQLGenerationResult(
            sql="SELECT 1",
            explanation="x",
            confidence=SQLGenerationConfidence.HIGH,
        )
    )

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
    )
    await use_case.execute(
        GenerateSQLRequest(question="q", database_kind=DatabaseKind.POSTGRESQL),
    )

    gen_call: SQLGenerationRequest = mock_generator.generate.await_args.args[0]
    assert gen_call.database_kind == DatabaseKind.POSTGRESQL
