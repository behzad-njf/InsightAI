"""Integration tests for POST /api/v1/ask."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from insightai.infrastructure.schema.loader import clear_schema_repository_cache
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION


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
    assert data["explainability"] is not None
    assert data["explainability"]["route"] == "sql"
    assert data["explainability"]["generation_source"] == data["generation_source"]
    assert isinstance(data["explainability"]["referenced_tables"], list)


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
