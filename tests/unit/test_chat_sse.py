"""Unit tests for chat SSE encoding."""

from __future__ import annotations

import json

from insightai.api.schemas.chat import ChatRequest, chat_stream_event_to_sse
from insightai.api.sse import format_sse
from insightai.domain.models.ask import AskStreamEvent, AskStreamPhase


def test_format_sse_includes_event_and_json_data() -> None:
    message = format_sse("token", {"text": "hi"})
    assert message.startswith("event: token\n")
    assert "data: " in message
    assert message.endswith("\n\n")
    data_line = [line for line in message.split("\n") if line.startswith("data: ")][0]
    assert json.loads(data_line.removeprefix("data: ")) == {"text": "hi"}


def test_chat_stream_status_event_mapping() -> None:
    event_name, data = chat_stream_event_to_sse(
        AskStreamEvent.status(AskStreamPhase.GENERATING_SQL),
        request=ChatRequest(question="Q?"),
    )
    assert event_name == "status"
    assert data["phase"] == "generating_sql"


def test_chat_stream_token_event_mapping() -> None:
    event_name, data = chat_stream_event_to_sse(
        AskStreamEvent.token("Hello"),
        request=ChatRequest(question="Q?"),
    )
    assert event_name == "token"
    assert data["text"] == "Hello"


def test_chat_stream_error_event_mapping() -> None:
    event_name, data = chat_stream_event_to_sse(
        AskStreamEvent.failure("bad", error_code="sql_generation_error"),
        request=ChatRequest(question="Q?"),
    )
    assert event_name == "error"
    assert data["error_message"] == "bad"
    assert data["error_code"] == "sql_generation_error"
