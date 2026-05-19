"""Integration tests for rate limiting on protected routes."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_settings


@pytest.fixture
def rate_limited_client() -> Generator[TestClient, None, None]:
    settings = make_settings(
        groq_api_key="gsk-rate-limit",
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    from insightai.main import create_app

    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch(
            "insightai.main.build_ai_components",
            return_value=MagicMock(),
        ),
        patch(
            "insightai.main.build_database_components",
            return_value=MagicMock(),
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client


def test_rate_limit_returns_429_with_retry_after(rate_limited_client: TestClient) -> None:
    for _ in range(2):
        response = rate_limited_client.post("/api/v1/chat/sessions", json={})
        assert response.status_code == 201

    blocked = rate_limited_client.post("/api/v1/chat/sessions", json={})
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"] == "RATE_LIMIT_EXCEEDED"
    assert body["retry_after_seconds"] >= 1
    assert blocked.headers.get("retry-after") == str(body["retry_after_seconds"])


def test_health_not_rate_limited(rate_limited_client: TestClient) -> None:
    for _ in range(5):
        assert rate_limited_client.get("/api/v1/health").status_code == 200
