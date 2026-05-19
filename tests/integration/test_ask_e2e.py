"""Phase 6.4 — end-to-end ask: generate SQL → execute → answer on SQLite."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from insightai.application.use_cases.ask import AskUseCase
from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.models.ask import AskRequest
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.infrastructure.ai.answer_generator import LLMAnswerGenerator
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.prompts.loader import (
    load_answer_generation_prompts,
    load_sql_generation_prompts,
)
from insightai.infrastructure.schema.loader import (
    clear_schema_repository_cache,
    get_schema_repository,
)
from tests.conftest import make_settings
from tests.fixtures.answer_generation_samples import CLASSROOM_ANSWER_LLM_JSON
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION
from tests.fixtures.sqlite_e2e_schema import CLASSROOM_SQLITE_LLM_JSON, seed_classroom_sqlite

pytestmark = pytest.mark.integration

SQLITE_MEMORY_URL = "sqlite:///:memory:"


@pytest.fixture
def ask_e2e_stack() -> Generator:
    settings = make_settings(
        groq_api_key="gsk-ask-e2e",
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url=SQLITE_MEMORY_URL,
        sql_max_rows=100,
        answer_max_prompt_rows=50,
    )
    components = build_database_components(settings)
    seed_classroom_sqlite(components.engine)

    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        side_effect=[
            LLMResponse(
                content=CLASSROOM_SQLITE_LLM_JSON,
                model="test-sql",
                provider=LLMProviderKind.GROQ,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                finish_reason="stop",
            ),
            LLMResponse(
                content=CLASSROOM_ANSWER_LLM_JSON,
                model="test-answer",
                provider=LLMProviderKind.GROQ,
                usage=TokenUsage(prompt_tokens=15, completion_tokens=25, total_tokens=40),
                finish_reason="stop",
            ),
        ],
    )

    sql_generator = LLMSQLGenerator(
        mock_framework,
        settings,
        prompt_bundle=load_sql_generation_prompts(settings),
        sql_validator=components.validator,
    )
    answer_generator = LLMAnswerGenerator(
        mock_framework,
        settings,
        prompt_bundle=load_answer_generation_prompts(settings),
    )
    ask = AskUseCase(
        GenerateSQLUseCase(
            BuildSchemaContextUseCase(get_schema_repository()),
            sql_generator,
            settings,
        ),
        RunQueryUseCase(
            components.executor,
            settings,
            sql_validator=components.validator,
            execution_defaults=components.execution_options,
        ),
        GenerateAnswerUseCase(answer_generator, settings),
        settings,
    )

    yield settings, ask
    components.engine.dispose()
    clear_schema_repository_cache()


@pytest.mark.asyncio
async def test_e2e_ask_full_pipeline_sqlite(ask_e2e_stack) -> None:
    _settings, ask = ask_e2e_stack
    clear_schema_repository_cache()

    with patch("insightai.api.deps.get_schema_repository") as mock_get_repo:
        mock_get_repo.side_effect = get_schema_repository
        result = await ask.execute(
            AskRequest(
                question=CLASSROOM_QUESTION,
                database_kind=DatabaseKind.SQLITE,
                max_context_tables=12,
            ),
        )

    assert result.sql.sql.has_sql
    assert result.execution.query_result.row_count == 2
    answer_text = result.answer.answer.answer.lower()
    assert "room a" in answer_text or "classroom" in answer_text
    assert result.answer.answer.row_count == 2
    assert result.timings.total_ms >= 0
    assert result.timings.sql_generation_ms >= 0
    assert result.timings.query_execution_ms >= 0
    assert result.timings.answer_generation_ms >= 0
