"""Integration tests for HTTP exception mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.exceptions import (
    AIFrameworkNotSupportedError,
    LLMProviderError,
    ReadOnlySQLViolationError,
    SQLGenerationParseError,
    SQLGenerationRejectedError,
)
from insightai.infrastructure.ai.factory import AIComponents
from tests.conftest import make_settings


@pytest.fixture
def client_with_failing_llm() -> TestClient:
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        side_effect=LLMProviderError("upstream model error"),
    )
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
            side_effect=ConfigurationError("no db"),
        ),
    ):
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client


def test_llm_provider_error_returns_502(client_with_failing_llm: TestClient) -> None:
    response = client_with_failing_llm.post(
        "/api/v1/ai/complete",
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert response.status_code == 502
    assert response.json()["error"] == "LLMProviderError"


def test_readonly_sql_exception_handler_via_route() -> None:
    """Simulate handler mapping using app exception handlers directly."""
    from insightai.main import create_app

    app = create_app()

    @app.get("/test-readonly-violation")
    def _raise_readonly() -> None:
        raise ReadOnlySQLViolationError("blocked", sql="DELETE FROM t", reason="blocked")

    client = TestClient(app)
    response = client.get("/test-readonly-violation")
    assert response.status_code == 400
    assert response.json()["error"] == "READ_ONLY_SQL_VIOLATION"


def test_sql_generation_rejected_handler() -> None:
    from insightai.main import create_app

    app = create_app()

    @app.get("/test-sql-rejected")
    def _raise_rejected() -> None:
        raise SQLGenerationRejectedError(
            "Disallowed keyword: DELETE",
            sql="DELETE FROM accounts_user",
            violations=["Disallowed keyword: DELETE"],
        )

    client = TestClient(app)
    response = client.get("/test-sql-rejected")
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "SQL_GENERATION_REJECTED"
    assert body["violations"]


def test_sql_generation_parse_handler() -> None:
    from insightai.main import create_app

    app = create_app()

    @app.get("/test-sql-parse")
    def _raise_parse() -> None:
        raise SQLGenerationParseError("invalid json from model")

    client = TestClient(app)
    response = client.get("/test-sql-parse")
    assert response.status_code == 422
    assert response.json()["error"] == "SQLGenerationParseError"


def test_framework_not_supported_handler() -> None:
    from insightai.main import create_app

    app = create_app()

    @app.get("/test-framework")
    def _raise_framework() -> None:
        raise AIFrameworkNotSupportedError("langchain not ready")

    client = TestClient(app)
    response = client.get("/test-framework")
    assert response.status_code == 501
