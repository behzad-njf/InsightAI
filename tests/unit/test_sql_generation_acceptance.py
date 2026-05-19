"""Phase 3 acceptance tests — mocked LLM, schema fixtures, read-only policy."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.domain.exceptions import SQLGenerationParseError, SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql import SQLStatementKind
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    SQLGenerationConfidence,
    SQLGenerationRequest,
)
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.prompts.loader import load_sql_generation_prompts
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from tests.conftest import make_settings
from tests.fixtures.sql_generation_samples import (
    CLASSROOM_LLM_JSON,
    CLASSROOM_QUESTION,
    CLASSROOM_SCHEMA_CONTEXT,
    CLASSROOM_TABLE_NAMES,
    INSUFFICIENT_LLM_JSON,
    INSUFFICIENT_SCHEMA_CONTEXT,
    NON_SELECT_SQL_CASES,
)


@pytest.fixture
def prompt_bundle():
    return load_sql_generation_prompts()


@pytest.fixture
def settings():
    return make_settings(groq_api_key="gsk-test", database_kind=DatabaseKind.MSSQL)


def _mock_framework(content: str, *, tokens: int = 200) -> MagicMock:
    framework = MagicMock()
    framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            model="llama-3.3-70b-versatile",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(
                prompt_tokens=tokens // 2,
                completion_tokens=tokens // 2,
                total_tokens=tokens,
            ),
            finish_reason="stop",
        )
    )
    return framework


@pytest.mark.asyncio
async def test_classroom_fixture_returns_plausible_select(prompt_bundle, settings) -> None:
    """Acceptance: fixture question + mock context → syntactically plausible SELECT."""
    generator = LLMSQLGenerator(
        _mock_framework(CLASSROOM_LLM_JSON, tokens=512),
        settings,
        prompt_bundle=prompt_bundle,
    )
    result = await generator.generate(
        SQLGenerationRequest(
            question=CLASSROOM_QUESTION,
            schema_context=CLASSROOM_SCHEMA_CONTEXT,
            database_kind=DatabaseKind.MSSQL,
            schema_table_names=CLASSROOM_TABLE_NAMES,
        )
    )

    assert result.has_sql is True
    sql_upper = result.sql.upper()
    assert sql_upper.startswith("SELECT")
    assert "TOP" in sql_upper
    assert "school_classroomchild" in result.sql
    assert "accounts_user" in result.sql
    assert result.confidence == SQLGenerationConfidence.HIGH
    assert set(result.tables_used) <= set(CLASSROOM_TABLE_NAMES)

    validation = create_sql_safety_validator().validate(result.sql)
    assert validation.is_valid is True
    assert validation.statement_kind == SQLStatementKind.SELECT


@pytest.mark.asyncio
async def test_token_usage_captured_from_mock_llm(prompt_bundle, settings) -> None:
    """Acceptance: token usage propagated to SQLGenerationResult."""
    generator = LLMSQLGenerator(
        _mock_framework(CLASSROOM_LLM_JSON, tokens=999),
        settings,
        prompt_bundle=prompt_bundle,
    )
    result = await generator.generate(
        SQLGenerationRequest(
            question=CLASSROOM_QUESTION,
            schema_context=CLASSROOM_SCHEMA_CONTEXT,
            database_kind=DatabaseKind.MSSQL,
        )
    )
    assert result.usage.total_tokens == 999
    assert result.usage.prompt_tokens == 499
    assert result.provider == LLMProviderKind.GROQ
    assert result.model == "llama-3.3-70b-versatile"


def test_prompts_loaded_from_files_not_hardcoded(prompt_bundle, settings) -> None:
    """Acceptance: prompts come from ``prompts/sql_generation/*.md``."""
    from insightai.infrastructure.prompts.loader import render_sql_generation_messages

    system_file = (
        settings.project_root / "prompts" / "sql_generation" / "system.md"
    ).read_text(encoding="utf-8")
    messages = render_sql_generation_messages(
        question="test",
        schema_context="### accounts_user",
        database_kind=DatabaseKind.MSSQL,
        settings=settings,
        bundle=prompt_bundle,
    )
    system_content = messages[0].content
    assert "read-only SQL" in system_file
    assert "read-only SQL" in system_content
    assert "JSON" in system_content
    assert "### accounts_user" in messages[1].content


@pytest.mark.asyncio
@pytest.mark.parametrize(("case_id", "bad_sql"), NON_SELECT_SQL_CASES)
async def test_mock_never_returns_non_select(
    case_id: str,
    bad_sql: str,
    prompt_bundle,
    settings,
) -> None:
    """Acceptance: non-SELECT mock responses are rejected before returning."""
    payload = json.dumps(
        {
            "sql": bad_sql,
            "explanation": f"unsafe {case_id}",
            "confidence": "high",
            "tables_used": ["accounts_user"],
        }
    )
    generator = LLMSQLGenerator(
        _mock_framework(payload),
        settings,
        prompt_bundle=prompt_bundle,
    )
    with pytest.raises(SQLGenerationRejectedError) as exc_info:
        await generator.generate(
            SQLGenerationRequest(
                question="Do something destructive",
                schema_context="### accounts_user\n- id",
                database_kind=DatabaseKind.MSSQL,
            )
        )
    assert exc_info.value.violations


@pytest.mark.asyncio
async def test_insufficient_schema_allows_empty_sql(prompt_bundle, settings) -> None:
    generator = LLMSQLGenerator(
        _mock_framework(INSUFFICIENT_LLM_JSON),
        settings,
        prompt_bundle=prompt_bundle,
    )
    result = await generator.generate(
        SQLGenerationRequest(
            question="What is the weather forecast?",
            schema_context=INSUFFICIENT_SCHEMA_CONTEXT,
            database_kind=DatabaseKind.MSSQL,
        )
    )
    assert result.has_sql is False
    assert result.confidence == SQLGenerationConfidence.LOW
    assert result.uncertainty_notes is not None


@pytest.mark.asyncio
async def test_invalid_llm_json_raises_parse_error(prompt_bundle, settings) -> None:
    generator = LLMSQLGenerator(
        _mock_framework("Sure! Here is your query: SELECT 1"),
        settings,
        prompt_bundle=prompt_bundle,
    )
    with pytest.raises(SQLGenerationParseError):
        await generator.generate(
            SQLGenerationRequest(
                question="List users",
                schema_context="### accounts_user",
                database_kind=DatabaseKind.MSSQL,
            )
        )


@pytest.mark.asyncio
async def test_generate_sql_use_case_end_to_end_mocked(settings) -> None:
    """Full orchestration: mocked schema context + mocked LLM."""
    schema_result = SchemaContextResult(
        question=CLASSROOM_QUESTION,
        tables=[],
        join_patterns=[],
        context_markdown=CLASSROOM_SCHEMA_CONTEXT,
        table_names=CLASSROOM_TABLE_NAMES,
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = schema_result

    mock_framework = _mock_framework(CLASSROOM_LLM_JSON)
    generator = LLMSQLGenerator(mock_framework, settings)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        generator,
        settings,
    )
    outcome = await use_case.execute(
        GenerateSQLRequest(question=CLASSROOM_QUESTION, max_context_tables=12),
    )

    assert outcome.schema_context.table_names == CLASSROOM_TABLE_NAMES
    assert outcome.sql.has_sql is True
    assert "school_classroomchild" in outcome.sql.sql
    mock_repository.build_context.assert_called_once()
    mock_framework.complete.assert_awaited_once()
