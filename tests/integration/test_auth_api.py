"""Integration tests for API authentication on protected routes."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.models.auth import ApiAuthMode
from insightai.domain.models.database import DatabaseKind
from tests.conftest import make_settings
from tests.fixtures.sql_generation_samples import CLASSROOM_QUESTION


@pytest.fixture
def chat_client_api_key_auth() -> Generator[TestClient, None, None]:
    settings = make_settings(
        groq_api_key="gsk-auth-test",
        api_auth_mode=ApiAuthMode.API_KEY,
        api_keys="test-api-key",
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
    )
    from insightai.main import create_app

    with patch("insightai.main.get_settings", return_value=settings), patch(
        "insightai.main.build_ai_components",
        return_value=MagicMock(),
    ), patch(
        "insightai.main.build_database_components",
        return_value=MagicMock(),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client


def test_health_unauthenticated(chat_client_api_key_auth: TestClient) -> None:
    response = chat_client_api_key_auth.get("/api/v1/health")
    assert response.status_code == 200


def test_chat_without_key_returns_401(chat_client_api_key_auth: TestClient) -> None:
    response = chat_client_api_key_auth.post(
        "/api/v1/chat",
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_protected_route_with_valid_api_key_header(chat_client_api_key_auth: TestClient) -> None:
    response = chat_client_api_key_auth.post(
        "/api/v1/chat/sessions",
        headers={"X-API-Key": "test-api-key"},
        json={"title": "Auth test"},
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Auth test"


def test_chat_with_invalid_api_key_returns_401(chat_client_api_key_auth: TestClient) -> None:
    response = chat_client_api_key_auth.post(
        "/api/v1/chat",
        headers={"X-API-Key": "wrong-key"},
        json={"question": CLASSROOM_QUESTION},
    )
    assert response.status_code == 401
