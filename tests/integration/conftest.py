"""Shared fixtures for integration tests (SQLite + mocked LLM pipeline)."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.exceptions import ConfigurationError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.infrastructure.ai.answer_generator import LLMAnswerGenerator
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.prompts.loader import (
    load_answer_generation_prompts,
    load_sql_generation_prompts,
)
from tests.conftest import make_settings
from tests.fixtures.answer_generation_samples import CLASSROOM_ANSWER_LLM_JSON
from tests.fixtures.sqlite_e2e_schema import CLASSROOM_SQLITE_LLM_JSON, seed_classroom_sqlite

SQLITE_MEMORY_URL = "sqlite:///:memory:"


@pytest.fixture
def ask_api_client() -> Generator[TestClient, None, None]:
    settings = make_settings(
        groq_api_key="gsk-ask-api",
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url=SQLITE_MEMORY_URL,
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

    from insightai.infrastructure.ai.factory import AIComponents

    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=mock_framework,
        sql_generator=sql_generator,
        answer_generator=answer_generator,
    )

    from insightai.main import create_app

    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch(
            "insightai.main.build_ai_components",
            return_value=ai,
        ),
        patch(
            "insightai.main.build_database_components",
            return_value=components,
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client

    components.engine.dispose()


@pytest.fixture
def ask_api_client_no_db() -> Generator[TestClient, None, None]:
    settings = make_settings(groq_api_key="gsk-ask-api")
    from insightai.infrastructure.ai.factory import AIComponents
    from insightai.main import create_app

    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=MagicMock(),
        sql_generator=MagicMock(),
        answer_generator=MagicMock(),
    )

    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch(
            "insightai.main.build_ai_components",
            return_value=ai,
        ),
        patch(
            "insightai.main.build_database_components",
            side_effect=ConfigurationError("database not configured"),
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client
