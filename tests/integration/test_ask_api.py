"""Integration tests for POST /api/v1/ask."""

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
from insightai.infrastructure.schema.loader import clear_schema_repository_cache
from tests.conftest import make_settings
from tests.fixtures.answer_generation_samples import CLASSROOM_ANSWER_LLM_JSON
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION
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

    with patch("insightai.main.get_settings", return_value=settings), patch(
        "insightai.main.build_ai_components",
        return_value=ai,
    ), patch(
        "insightai.main.build_database_components",
        return_value=components,
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

    with patch("insightai.main.get_settings", return_value=settings), patch(
        "insightai.main.build_ai_components",
        return_value=ai,
    ), patch(
        "insightai.main.build_database_components",
        side_effect=ConfigurationError("database not configured"),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client


def test_ask_success(ask_api_client: TestClient) -> None:
    clear_schema_repository_cache()
    with patch("insightai.api.deps.get_schema_repository") as mock_get:
        from insightai.infrastructure.schema.loader import get_schema_repository

        mock_get.side_effect = get_schema_repository

        response = ask_api_client.post(
            "/api/v1/ask",
            json={"question": CLASSROOM_QUESTION, "database_kind": "sqlite"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == CLASSROOM_QUESTION
    assert data["row_count"] == 2
    assert data["sql"].upper().startswith("SELECT")
    assert len(data["query_result"]["rows"]) == 2
    assert "classroom_id" in data["query_result"]["columns"]
    assert len(data["answer"]) > 0
    assert data["timings"]["total_ms"] >= 0
    assert data["timeout_seconds"] == 120
    assert data["sql_usage"]["total_tokens"] == 30
    assert data["answer_usage"]["total_tokens"] == 40


def test_ask_validation_error(ask_api_client: TestClient) -> None:
    response = ask_api_client.post("/api/v1/ask", json={"question": ""})
    assert response.status_code == 422


def test_ask_requires_database(ask_api_client_no_db: TestClient) -> None:
    response = ask_api_client_no_db.post(
        "/api/v1/ask",
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "ConfigurationError"
