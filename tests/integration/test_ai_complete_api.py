"""Integration tests for LLM complete endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.models.llm import LLMProviderKind, LLMResponse, LLMStreamChunk, TokenUsage
from insightai.infrastructure.ai.factory import AIComponents
from tests.conftest import make_settings
from tests.integration.sse_helpers import parse_sse


@pytest.fixture
def ai_client() -> TestClient:
    settings = make_settings(groq_api_key="gsk-test", debug=False)
    mock_framework = MagicMock()
    llm_response = LLMResponse(
        content="Hello from InsightAI",
        model="llama-3.3-70b-versatile",
        provider=LLMProviderKind.GROQ,
        usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        finish_reason="stop",
    )
    mock_framework.complete = AsyncMock(return_value=llm_response)

    async def _complete_stream(_request):
        yield LLMStreamChunk(text="Hello ")
        yield LLMStreamChunk(text="from InsightAI")
        yield LLMStreamChunk(finish_reason="stop", usage=llm_response.usage)

    mock_provider = MagicMock()
    mock_provider.provider_kind = LLMProviderKind.GROQ
    mock_provider.default_model = "llama-3.3-70b-versatile"
    mock_framework.complete_stream = _complete_stream
    mock_framework.get_llm_provider = MagicMock(return_value=mock_provider)
    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=mock_framework,
        sql_generator=MagicMock(),
        answer_generator=MagicMock(),
    )

    from insightai.domain.exceptions import ConfigurationError
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
        with TestClient(app) as test_client:
            yield test_client


def test_ai_complete(ai_client: TestClient) -> None:
    response = ai_client.post(
        "/api/v1/ai/complete",
        json={
            "messages": [{"role": "user", "content": "Say hello"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Hello from InsightAI"
    assert data["provider"] == "groq"
    assert data["usage"]["total_tokens"] == 8
    assert data.get("raw") is None


def test_ai_complete_validation_error(ai_client: TestClient) -> None:
    response = ai_client.post("/api/v1/ai/complete", json={"messages": []})
    assert response.status_code == 422


def test_ai_complete_stream(ai_client: TestClient) -> None:
    with ai_client.stream(
        "POST",
        "/api/v1/ai/complete/stream",
        json={"messages": [{"role": "user", "content": "Say hello"}]},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode()

    events = parse_sse(body)
    assert [name for name, _ in events] == ["token", "token", "done"]
    assert events[0][1]["text"] == "Hello "
    assert events[-1][1]["content"] == "Hello from InsightAI"
    assert events[-1][1]["provider"] == "groq"
