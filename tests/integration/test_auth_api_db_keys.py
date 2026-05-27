"""Integration tests: HTTP auth via app-database API keys (Phase 16.4)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from insightai.domain.models.api_key import CreateApiKeyRequest
from insightai.domain.models.auth import ApiAuthMode, ApiKeyAuthSource
from insightai.infrastructure.app_db.bootstrap import build_app_database_components
from insightai.infrastructure.config.settings import Settings, clear_settings_cache
from tests.conftest import mock_governance_components


@pytest.fixture
def db_auth_client(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, str], None, None]:
    db_file = tmp_path / "auth_api.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")

    app_db = build_app_database_components(Settings(_env_file=None))  # type: ignore[arg-type,call-arg]
    created = app_db.api_key_store.create(
        CreateApiKeyRequest(label="Integration test key", roles=["analyst"]),
    )

    settings = Settings(
        _env_file=None,  # type: ignore[arg-type,call-arg]
        groq_api_key="gsk-auth-test",
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
        api_keys=None,
        database_readonly_url="sqlite:///:memory:",
    )

    from insightai.main import create_app

    governance = mock_governance_components()
    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch("insightai.main.build_ai_components", return_value=MagicMock()),
        patch("insightai.main.build_database_components", return_value=MagicMock()),
        patch("insightai.main.build_app_database_components", return_value=app_db),
        patch("insightai.main.build_governance_components", return_value=governance),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield client, created.secret


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_chat_with_db_api_key(
    db_auth_client: tuple[TestClient, str],
) -> None:
    client, secret = db_auth_client
    response = client.post(
        "/api/v1/chat/sessions",
        headers={"X-API-Key": secret},
        json={"title": "DB auth session"},
    )
    assert response.status_code == 201
    assert response.json()["title"] == "DB auth session"


def test_chat_without_db_key_returns_401(
    db_auth_client: tuple[TestClient, str],
) -> None:
    client, _secret = db_auth_client
    response = client.post(
        "/api/v1/chat/sessions",
        json={"title": "No auth"},
    )
    assert response.status_code == 401
