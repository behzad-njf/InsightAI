"""Shared pytest fixtures and helpers."""

from __future__ import annotations

pytest_plugins = ["tests.integration.chat_product_fixtures"]

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.exceptions import ConfigurationError
from insightai.domain.models.database import DatabaseHealthStatus, DatabaseKind
from insightai.infrastructure.config.settings import Settings, clear_settings_cache


def make_settings(**overrides: Any) -> Settings:
    """Build settings without loading the repo ``.env`` file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type,call-arg]


def mock_app_database_components() -> MagicMock:
    """App DB mock that does not treat MagicMock.verify as a valid key."""
    mock = MagicMock()
    mock.api_key_store.verify.return_value = None
    return mock


def mock_governance_components() -> MagicMock:
    from insightai.infrastructure.governance.noop_enforcer import NoOpGovernanceEnforcer

    mock = MagicMock()
    mock.enforcer = NoOpGovernanceEnforcer()
    return mock


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def test_settings() -> Settings:
    return make_settings(
        groq_api_key="gsk-test-key",
        openai_api_key="sk-test-key",
        database_readonly_url="sqlite:///:memory:",
        database_kind=DatabaseKind.SQLITE,
    )


@pytest.fixture
def mock_database_components() -> MagicMock:
    components = MagicMock()
    components.config.kind = DatabaseKind.SQLITE
    components.health_check.check.return_value = DatabaseHealthStatus(
        healthy=True,
        kind=DatabaseKind.SQLITE,
        latency_ms=2.5,
    )
    return components


@pytest.fixture
def mock_ai_components() -> MagicMock:
    return MagicMock()


@pytest.fixture
def api_client(
    test_settings: Settings,
    mock_ai_components: MagicMock,
    mock_database_components: MagicMock,
) -> Generator[TestClient, None, None]:
    """FastAPI test client with AI/DB startup mocked."""
    from insightai.main import create_app

    with (
        patch("insightai.main.get_settings", return_value=test_settings),
        patch(
            "insightai.main.build_ai_components",
            return_value=mock_ai_components,
        ),
        patch(
            "insightai.main.build_database_components",
            return_value=mock_database_components,
        ),
        patch(
            "insightai.main.build_app_database_components",
            return_value=mock_app_database_components(),
        ),
        patch(
            "insightai.main.build_governance_components",
            return_value=mock_governance_components(),
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client


@pytest.fixture
def api_client_no_database(
    test_settings: Settings,
    mock_ai_components: MagicMock,
) -> Generator[TestClient, None, None]:
    """API client simulating missing database configuration at startup."""
    from insightai.main import create_app

    with (
        patch("insightai.main.get_settings", return_value=test_settings),
        patch(
            "insightai.main.build_ai_components",
            return_value=mock_ai_components,
        ),
        patch(
            "insightai.main.build_database_components",
            side_effect=ConfigurationError("Database URL not configured."),
        ),
        patch(
            "insightai.main.build_app_database_components",
            return_value=mock_app_database_components(),
        ),
        patch(
            "insightai.main.build_governance_components",
            return_value=mock_governance_components(),
        ),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client
