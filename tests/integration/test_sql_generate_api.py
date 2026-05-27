"""Integration tests for POST /api/v1/sql/generate."""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.exceptions import ConfigurationError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.infrastructure.ai.factory import AIComponents
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.prompts.loader import load_sql_generation_prompts
from insightai.infrastructure.schema.loader import clear_schema_repository_cache
from tests.conftest import make_settings
from tests.fixtures.sql_generation_samples import CLASSROOM_LLM_JSON, CLASSROOM_QUESTION


@pytest.fixture
def sql_generate_client() -> Generator[TestClient, None, None]:
    settings = make_settings(groq_api_key="gsk-test", database_kind=DatabaseKind.MSSQL)
    prompt_bundle = load_sql_generation_prompts(settings)

    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=CLASSROOM_LLM_JSON,
            model="llama-3.3-70b-versatile",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80),
            finish_reason="stop",
        )
    )
    sql_generator = LLMSQLGenerator(
        mock_framework,
        settings,
        prompt_bundle=prompt_bundle,
    )
    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=mock_framework,
        sql_generator=sql_generator,
        answer_generator=MagicMock(),
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
            side_effect=ConfigurationError("skip db"),
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client


def test_sql_generate_success(sql_generate_client: TestClient) -> None:
    clear_schema_repository_cache()
    with patch("insightai.api.deps.get_schema_repository") as mock_get:
        from insightai.infrastructure.schema.loader import get_schema_repository

        mock_get.side_effect = get_schema_repository

        response = sql_generate_client.post(
            "/api/v1/sql/generate",
            json={
                "question": CLASSROOM_QUESTION,
                "max_context_tables": 12,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == CLASSROOM_QUESTION
    assert data["sql"].upper().startswith("SELECT")
    assert "school_classroomchild" in data["sql"]
    assert data["confidence"] == "high"
    assert data["usage"]["total_tokens"] == 80
    assert "demo_orders" in data["schema_table_names"]
    assert "demo_customers" in data["schema_table_names"]
    assert len(data["context_markdown"]) > 0


def test_sql_generate_rejects_unsafe_sql(sql_generate_client: TestClient) -> None:
    clear_schema_repository_cache()
    sql_generate_client.app.state.ai.framework.complete = AsyncMock(
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

    with patch("insightai.api.deps.get_schema_repository") as mock_get:
        from insightai.infrastructure.schema.loader import get_schema_repository

        mock_get.side_effect = get_schema_repository

        response = sql_generate_client.post(
            "/api/v1/sql/generate",
            json={"question": "Remove all users"},
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "SQL_GENERATION_REJECTED"
    assert data["violations"]


def test_sql_generate_validation_error(sql_generate_client: TestClient) -> None:
    response = sql_generate_client.post("/api/v1/sql/generate", json={"question": ""})
    assert response.status_code == 422
