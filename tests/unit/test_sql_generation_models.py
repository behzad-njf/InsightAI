"""Unit tests for SQL generation domain models and port contract."""

from __future__ import annotations

import pytest

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, TokenUsage
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql_generation import (
    SQLGenerationConfidence,
    SQLGenerationLLMOutput,
    SQLGenerationRequest,
    SQLGenerationResult,
)
from insightai.domain.ports.sql_generator import ISQLGenerator


def test_request_from_schema_context() -> None:
    context = SchemaContextResult(
        question="children in classroom",
        tables=[],
        join_patterns=[],
        context_markdown="### accounts_user\n- id",
        table_names=["accounts_user", "school_classroomchild"],
    )
    request = SQLGenerationRequest.from_schema_context(
        question="How many children are in a classroom?",
        context=context,
        database_kind=DatabaseKind.MSSQL,
        max_rows=100,
    )
    assert request.question == "How many children are in a classroom?"
    assert "### accounts_user" in request.schema_context
    assert request.schema_table_names == ["accounts_user", "school_classroomchild"]
    assert request.database_kind == DatabaseKind.MSSQL
    assert request.max_rows == 100


def test_request_requires_non_empty_question_and_context() -> None:
    with pytest.raises(ValueError):
        SQLGenerationRequest(
            question="",
            schema_context="tables",
            database_kind=DatabaseKind.MSSQL,
        )
    with pytest.raises(ValueError):
        SQLGenerationRequest(
            question="hi",
            schema_context="",
            database_kind=DatabaseKind.MSSQL,
        )


def test_llm_output_normalizes_confidence() -> None:
    output = SQLGenerationLLMOutput.model_validate(
        {
            "sql": "SELECT TOP 10 id FROM accounts_user",
            "explanation": "Lists users.",
            "confidence": "HIGH",
            "tables_used": ["accounts_user"],
        }
    )
    assert output.confidence == SQLGenerationConfidence.HIGH
    assert output.sql.startswith("SELECT")


def test_result_from_llm_output_carries_usage() -> None:
    output = SQLGenerationLLMOutput(
        sql="SELECT 1",
        explanation="test",
        confidence=SQLGenerationConfidence.LOW,
        uncertainty_notes="ambiguous filter",
        tables_used=["accounts_user"],
    )
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    result = SQLGenerationResult.from_llm_output(
        output,
        schema_table_names=["accounts_user"],
        usage=usage,
        model="llama-3.3-70b-versatile",
        provider=LLMProviderKind.GROQ,
        finish_reason="stop",
    )
    assert result.has_sql is True
    assert result.usage.total_tokens == 30
    assert result.provider == LLMProviderKind.GROQ
    assert result.uncertainty_notes == "ambiguous filter"


def test_result_has_sql_false_for_empty_string() -> None:
    result = SQLGenerationResult(
        sql="   ",
        explanation="Cannot answer",
        confidence=SQLGenerationConfidence.LOW,
    )
    assert result.has_sql is False


def test_sql_generator_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        ISQLGenerator()  # type: ignore[abstract]
