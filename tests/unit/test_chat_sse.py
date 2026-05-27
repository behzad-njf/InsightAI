"""Unit tests for chat SSE encoding."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from insightai.api.schemas.chat import ChatRequest, chat_stream_event_to_sse
from insightai.api.sse import format_sse
from insightai.domain.models.answer import AnswerGenerationResult, GenerateAnswerResult
from insightai.domain.models.ask import AskResult, AskStreamEvent, AskStreamPhase, AskTimings
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.explainability import ExplainabilityPayload
from insightai.domain.models.hybrid import QueryRouteKind


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


def test_chat_stream_done_includes_explainability_payload() -> None:
    answer = GenerateAnswerResult(
        question="q",
        sql="SELECT 1",
        query_result=QueryResult(
            columns=[QueryColumn(name="n")],
            rows=[{"n": 1}],
            row_count=1,
            executed_at=datetime.now(UTC),
            truncated=False,
        ),
        answer=AnswerGenerationResult(answer="ok", row_count=1, truncation_noted=False),
    )
    result = AskResult(
        question="q",
        route=QueryRouteKind.SQL,
        answer=answer,
        timings=AskTimings(
            sql_generation_ms=1.0,
            query_execution_ms=1.0,
            answer_generation_ms=1.0,
            total_ms=3.0,
        ),
        explainability=ExplainabilityPayload(question="q", route=QueryRouteKind.SQL),
    )
    event_name, data = chat_stream_event_to_sse(
        AskStreamEvent.done(result),
        request=ChatRequest(question="q"),
    )
    assert event_name == "done"
    assert data["explainability"] is not None
    assert data["explainability"]["route"] == "sql"
