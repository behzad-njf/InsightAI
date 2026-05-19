"""
Phase 7.6 — product chat E2E: session → chat → history with mocked LLM + SQLite.

Exercises the full protected API stack (auth/rate-limit variants in dedicated tests).
"""

from __future__ import annotations

import pytest

from insightai.infrastructure.schema.loader import clear_schema_repository_cache
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION
from tests.integration.chat_product_fixtures import (
    build_product_chat_client,
    dispose_product_client,
)
from tests.integration.sse_helpers import parse_sse

pytestmark = pytest.mark.integration


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def test_product_e2e_chat_stream_disabled_returns_404() -> None:
    client, components, stack = build_product_chat_client(chat_streaming_enabled=False)
    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={"question": CLASSROOM_QUESTION},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "not_found"
    finally:
        dispose_product_client(components, stack)


def test_product_e2e_chat_stream(product_chat_client) -> None:
    """POST /chat/stream returns SSE status, tokens, and done."""
    clear_schema_repository_cache()
    with product_chat_client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"question": CLASSROOM_QUESTION},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode()

    events = parse_sse(body)
    kinds = [name for name, _ in events]
    assert kinds[0] == "status"
    assert kinds[1] == "status"
    assert kinds[2] == "status"
    assert "token" in kinds
    assert kinds[-1] == "done"
    done_data = events[-1][1]
    assert done_data["question"] == CLASSROOM_QUESTION
    assert len(done_data["answer"]) > 0
    assert done_data["row_count"] == 2
    assert done_data["timings"]["total_ms"] >= 0


def test_product_e2e_stateless_chat(product_chat_client) -> None:
    """POST /chat without session — answer + timings, no history."""
    clear_schema_repository_cache()
    response = product_chat_client.post(
        "/api/v1/chat",
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == CLASSROOM_QUESTION
    assert len(data["answer"]) > 0
    assert data["row_count"] == 2
    assert data["session_id"] is None
    assert data["sql"] is None
    assert data["data"] is None
    assert response.headers.get("X-Request-ID") == data["request_id"]
    assert data["timings"]["sql_generation_ms"] >= 0
    assert data["timings"]["query_execution_ms"] >= 0
    assert data["timings"]["answer_generation_ms"] >= 0
    assert data["timings"]["total_ms"] >= 0


def test_product_e2e_session_create_chat_and_history(product_chat_client) -> None:
    """Full product flow: session → chat → message history."""
    clear_schema_repository_cache()

    session_resp = product_chat_client.post(
        "/api/v1/chat/sessions",
        json={"title": "Classroom analytics"},
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    chat_resp = product_chat_client.post(
        "/api/v1/chat",
        json={
            "question": CLASSROOM_QUESTION,
            "session_id": session_id,
            "include_sql": True,
        },
    )
    assert chat_resp.status_code == 200
    chat = chat_resp.json()
    assert chat["session_id"] == session_id
    assert chat["sql"].upper().startswith("SELECT")
    assert chat["row_count"] == 2

    history = product_chat_client.get(f"/api/v1/chat/sessions/{session_id}/messages")
    assert history.status_code == 200
    messages = history.json()
    assert messages["session_id"] == session_id
    assert messages["total"] == 2
    assert len(messages["messages"]) == 2
    assert messages["messages"][0]["role"] == "user"
    assert messages["messages"][0]["content"] == CLASSROOM_QUESTION
    assert messages["messages"][1]["role"] == "assistant"
    assert "room" in messages["messages"][1]["content"].lower()
    assert messages["messages"][1]["sql"] is not None

    get_session = product_chat_client.get(f"/api/v1/chat/sessions/{session_id}")
    assert get_session.status_code == 200
    assert get_session.json()["message_count"] == 2


def test_product_e2e_multiturn_session(product_chat_client) -> None:
    """Two chat turns append four messages to session history."""
    clear_schema_repository_cache()

    session_id = product_chat_client.post("/api/v1/chat/sessions", json={}).json()["id"]
    q1 = CLASSROOM_QUESTION
    q2 = "How many classrooms are in the result?"

    for question in (q1, q2):
        resp = product_chat_client.post(
            "/api/v1/chat",
            json={"question": question, "session_id": session_id},
        )
        assert resp.status_code == 200

    history = product_chat_client.get(f"/api/v1/chat/sessions/{session_id}/messages")
    assert history.status_code == 200
    assert history.json()["total"] == 4
    assert len(history.json()["messages"]) == 4


def test_product_e2e_with_api_key_auth(product_chat_client_auth) -> None:
    """Authenticated product flow: session + chat + history."""
    client, api_key = product_chat_client_auth
    headers = _auth_headers(api_key)
    clear_schema_repository_cache()

    unauthorized = client.post("/api/v1/chat", json={"question": CLASSROOM_QUESTION})
    assert unauthorized.status_code == 401

    session_id = client.post(
        "/api/v1/chat/sessions",
        headers=headers,
        json={},
    ).json()["id"]

    chat = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": CLASSROOM_QUESTION, "session_id": session_id},
    )
    assert chat.status_code == 200
    assert chat.json()["session_id"] == session_id

    history = client.get(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2


def test_product_e2e_session_header_alias(product_chat_client) -> None:
    """X-Session-ID header works instead of JSON session_id."""
    clear_schema_repository_cache()
    session_id = product_chat_client.post("/api/v1/chat/sessions", json={}).json()["id"]

    response = product_chat_client.post(
        "/api/v1/chat",
        headers={"X-Session-ID": session_id},
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_product_e2e_delete_session(product_chat_client) -> None:
    clear_schema_repository_cache()
    session_id = product_chat_client.post("/api/v1/chat/sessions", json={}).json()["id"]
    assert product_chat_client.delete(f"/api/v1/chat/sessions/{session_id}").status_code == 204
    assert product_chat_client.get(f"/api/v1/chat/sessions/{session_id}").status_code == 404


def test_product_e2e_auth_and_rate_limit() -> None:
    """Protected stack: auth passes, third request within window is rate limited."""
    client, components, stack = build_product_chat_client(
        api_auth_mode="api_key",
        api_keys="rate-e2e-key",
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    headers = _auth_headers("rate-e2e-key")
    try:
        clear_schema_repository_cache()
        for _ in range(2):
            assert client.post("/api/v1/chat/sessions", headers=headers, json={}).status_code == 201
        blocked = client.post("/api/v1/chat/sessions", headers=headers, json={})
        assert blocked.status_code == 429
        assert blocked.json()["error"] == "RATE_LIMIT_EXCEEDED"
        assert int(blocked.headers.get("retry-after", "0")) >= 1
    finally:
        dispose_product_client(components, stack)


def test_product_e2e_health_unaffected_by_product_limits() -> None:
    """Health stays public when auth + rate limits are enabled on product routes."""
    client, components, stack = build_product_chat_client(
        api_auth_mode="api_key",
        api_keys="health-key",
        rate_limit_enabled=True,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
    )
    try:
        for _ in range(3):
            assert client.get("/api/v1/health").status_code == 200
    finally:
        dispose_product_client(components, stack)
