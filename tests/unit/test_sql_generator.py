"""Unit tests for LLMSQLGenerator (mocked framework)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.domain.exceptions import SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import (
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from insightai.domain.models.sql_generation import (
    SQLGenerationConfidence,
    SQLGenerationRequest,
)
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.prompts.loader import load_sql_generation_prompts
from tests.conftest import make_settings

_LLM_JSON = json.dumps(
    {
        "sql": "SELECT TOP 5 id FROM school_classroomchild",
        "explanation": "Lists classroom child ids.",
        "confidence": "medium",
        "uncertainty_notes": None,
        "tables_used": ["school_classroomchild"],
    }
)


@pytest.fixture
def prompt_bundle():
    return load_sql_generation_prompts()


@pytest.mark.asyncio
async def test_generate_returns_parsed_result(prompt_bundle) -> None:
    settings = make_settings(groq_api_key="gsk-test", sql_max_rows=100)
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=_LLM_JSON,
            model="llama-3.3-70b-versatile",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            finish_reason="stop",
        )
    )

    generator = LLMSQLGenerator(
        mock_framework,
        settings,
        prompt_bundle=prompt_bundle,
    )
    request = SQLGenerationRequest(
        question="List children in classrooms",
        schema_context="### school_classroomchild\n- id",
        database_kind=DatabaseKind.MSSQL,
        schema_table_names=["school_classroomchild"],
    )
    result = await generator.generate(request)

    assert result.has_sql is True
    assert "school_classroomchild" in result.sql
    assert result.confidence == SQLGenerationConfidence.MEDIUM
    assert result.usage.total_tokens == 150
    assert result.provider == LLMProviderKind.GROQ
    assert result.schema_table_names == ["school_classroomchild"]

    call_args = mock_framework.complete.await_args
    assert call_args is not None
    llm_request: LLMRequest = call_args.args[0]
    assert len(llm_request.messages) == 2
    assert llm_request.messages[0].role.value == "system"
    assert "List children in classrooms" in llm_request.messages[1].content
    assert llm_request.max_tokens == 4096


@pytest.mark.asyncio
async def test_generate_propagates_llm_errors(prompt_bundle) -> None:
    from insightai.domain.exceptions import LLMProviderError

    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(side_effect=LLMProviderError("api error"))

    generator = LLMSQLGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)
    request = SQLGenerationRequest(
        question="Count users",
        schema_context="### accounts_user",
        database_kind=DatabaseKind.MSSQL,
    )

    with pytest.raises(LLMProviderError):
        await generator.generate(request)


@pytest.mark.asyncio
async def test_generate_rejects_non_select_sql(prompt_bundle) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "sql": "DELETE FROM accounts_user",
                    "explanation": "bad",
                    "confidence": "high",
                    "tables_used": [],
                }
            ),
            model="test",
            provider=LLMProviderKind.GROQ,
        )
    )
    generator = LLMSQLGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)

    with pytest.raises(SQLGenerationRejectedError):
        await generator.generate(
            SQLGenerationRequest(
                question="Remove users",
                schema_context="### accounts_user",
                database_kind=DatabaseKind.MSSQL,
            )
        )


@pytest.mark.asyncio
async def test_generate_extracts_sql_from_fenced_field(prompt_bundle) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    fenced_sql = "```sql\nSELECT TOP 3 id FROM accounts_user\n```"
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "sql": fenced_sql,
                    "explanation": "ok",
                    "confidence": "high",
                    "tables_used": ["accounts_user"],
                }
            ),
            model="test",
            provider=LLMProviderKind.GROQ,
        )
    )
    generator = LLMSQLGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)
    result = await generator.generate(
        SQLGenerationRequest(
            question="List users",
            schema_context="### accounts_user",
            database_kind=DatabaseKind.MSSQL,
        )
    )
    assert result.sql == "SELECT TOP 3 id FROM accounts_user"
