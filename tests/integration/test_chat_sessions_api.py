"""Integration tests for chat session CRUD and history (Phase 7.3)."""

from __future__ import annotations

from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION
from tests.integration.test_ask_api import ask_api_client


def test_session_crud_and_chat_history(ask_api_client) -> None:
    create = ask_api_client.post("/api/v1/chat/sessions", json={"title": "Classrooms"})
    assert create.status_code == 201
    session_id = create.json()["id"]

    get_resp = ask_api_client.get(f"/api/v1/chat/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Classrooms"
    assert get_resp.json()["message_count"] == 0

    chat = ask_api_client.post(
        "/api/v1/chat",
        json={"question": CLASSROOM_QUESTION, "session_id": session_id},
    )
    assert chat.status_code == 200
    assert chat.json()["session_id"] == session_id

    messages = ask_api_client.get(f"/api/v1/chat/sessions/{session_id}/messages")
    assert messages.status_code == 200
    body = messages.json()
    assert body["total"] == 2
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
    assert CLASSROOM_QUESTION in body["messages"][0]["content"]

    delete = ask_api_client.delete(f"/api/v1/chat/sessions/{session_id}")
    assert delete.status_code == 204

    missing = ask_api_client.get(f"/api/v1/chat/sessions/{session_id}")
    assert missing.status_code == 404


def test_chat_unknown_session_returns_404(ask_api_client) -> None:
    response = ask_api_client.post(
        "/api/v1/chat",
        json={
            "question": CLASSROOM_QUESTION,
            "session_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"] == "CHAT_SESSION_NOT_FOUND"


def test_chat_session_header(ask_api_client) -> None:
    create = ask_api_client.post("/api/v1/chat/sessions")
    assert create.status_code == 201
    session_id = create.json()["id"]

    response = ask_api_client.post(
        "/api/v1/chat",
        headers={"X-Session-ID": session_id},
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
