"""
Chat streaming E2E — SSE auth, rate limits, sessions (Phase 7 + streaming).

Requires: mocked LLM + SQLite (see ``chat_product_fixtures``).
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

pytestmark = [pytest.mark.integration, pytest.mark.streaming]


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _stream_chat(
    client,
    *,
    headers: dict[str, str] | None = None,
    **json_body: object,
) -> list[tuple[str, dict]]:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        headers=headers or {},
        json=json_body,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return parse_sse(response.read().decode())


def test_stream_requires_api_key_when_auth_enabled(product_chat_client_auth) -> None:
    client, api_key = product_chat_client_auth
    clear_schema_repository_cache()

    denied = client.post(
        "/api/v1/chat/stream",
        json={"question": CLASSROOM_QUESTION},
    )
    assert denied.status_code == 401

    events = _stream_chat(
        client,
        headers=_auth_headers(api_key),
        question=CLASSROOM_QUESTION,
    )
    assert events[-1][0] == "done"
    assert events[-1][1]["row_count"] == 2


def test_stream_rate_limited_with_auth() -> None:
    client, components, stack = build_product_chat_client(
        api_auth_mode="api_key",
        api_keys="stream-rate-key",
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    headers = _auth_headers("stream-rate-key")
    try:
        clear_schema_repository_cache()
        for _ in range(2):
            events = _stream_chat(
                client,
                headers=headers,
                question=CLASSROOM_QUESTION,
            )
            assert events[-1][0] == "done"

        blocked = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"question": CLASSROOM_QUESTION},
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"] == "RATE_LIMIT_EXCEEDED"
    finally:
        dispose_product_client(components, stack)


def test_stream_session_history_recorded_on_done(product_chat_client_auth) -> None:
    client, api_key = product_chat_client_auth
    headers = _auth_headers(api_key)
    clear_schema_repository_cache()

    session_id = client.post(
        "/api/v1/chat/sessions",
        headers=headers,
        json={"title": "Stream session"},
    ).json()["id"]

    events = _stream_chat(
        client,
        headers=headers,
        question=CLASSROOM_QUESTION,
        session_id=session_id,
        include_sql=True,
    )
    assert events[-1][0] == "done"
    done = events[-1][1]
    assert done["session_id"] == session_id
    assert done["sql"] is not None
    assert done["sql"].upper().startswith("SELECT")

    history = client.get(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert "classroom" in history.json()["messages"][1]["content"].lower()


def test_stream_status_phases_in_order(product_chat_client_auth) -> None:
    client, api_key = product_chat_client_auth
    clear_schema_repository_cache()

    events = _stream_chat(
        client,
        headers=_auth_headers(api_key),
        question=CLASSROOM_QUESTION,
    )
    status_phases = [data["phase"] for name, data in events if name == "status"]
    assert status_phases == [
        "generating_sql",
        "executing_query",
        "generating_answer",
    ]
