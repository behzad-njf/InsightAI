"""Integration tests for POST /api/v1/chat (Phase 7)."""

from __future__ import annotations

from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION


def test_chat_returns_answer(ask_api_client) -> None:
    response = ask_api_client.post(
        "/api/v1/chat",
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == CLASSROOM_QUESTION
    assert len(data["answer"]) > 0
    assert data["row_count"] == 2
    assert data["sql"] is None
    assert data["data"] is None
    assert "request_id" in data
    assert response.headers.get("X-Request-ID") == data["request_id"]
    assert data["timings"]["total_ms"] >= 0
    assert data["explainability"] is not None
    assert data["explainability"]["route"] in {"sql", "rag", "both"}
    assert data["explainability"]["generation_source"] == data["generation_source"]


def test_chat_include_sql_and_data(ask_api_client) -> None:
    response = ask_api_client.post(
        "/api/v1/chat",
        json={
            "question": CLASSROOM_QUESTION,
            "include_sql": True,
            "include_data": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sql"].upper().startswith("SELECT")
    assert data["data"]["row_count"] == 2
    assert "classroom_id" in data["data"]["columns"]
    assert data["explainability"] is not None
    assert data["explainability"]["generation_source"] == data["generation_source"]


def test_chat_question_too_long(ask_api_client) -> None:
    response = ask_api_client.post(
        "/api/v1/chat",
        json={"question": "x" * 5000},
    )
    assert response.status_code == 422


def test_chat_requires_database(ask_api_client_no_db) -> None:
    response = ask_api_client_no_db.post(
        "/api/v1/chat",
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 503
