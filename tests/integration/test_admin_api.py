"""Admin API and revoked-key tests (Phase 16.5–16.6)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from insightai.domain.models.api_key import CreateApiKeyRequest, PlatformRole
from insightai.domain.models.auth import ApiAuthMode, ApiKeyAuthSource
from insightai.infrastructure.app_db.bootstrap import build_app_database_components
from insightai.infrastructure.config.settings import Settings, clear_settings_cache
from tests.conftest import mock_governance_components


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def admin_client(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, str, str], None, None]:
    db_file = tmp_path / "admin_api.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")

    app_db = build_app_database_components(Settings(_env_file=None))  # type: ignore[arg-type,call-arg]
    admin_created = app_db.api_key_store.create(
        CreateApiKeyRequest(label="Admin key", roles=[PlatformRole.ADMIN.value]),
    )
    analyst_created = app_db.api_key_store.create(
        CreateApiKeyRequest(
            label="Analyst key",
            roles=[PlatformRole.ANALYST.value],
            attributes={"campus_ids": ["1"]},
        ),
    )

    settings = Settings(
        _env_file=None,  # type: ignore[arg-type,call-arg]
        groq_api_key="gsk-test",
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
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
            yield client, admin_created.secret, analyst_created.secret


def test_admin_list_keys_requires_admin_role(
    admin_client: tuple[TestClient, str, str],
) -> None:
    client, admin_secret, analyst_secret = admin_client

    denied = client.get(
        "/api/v1/admin/keys",
        headers={"X-API-Key": analyst_secret},
    )
    assert denied.status_code == 403
    body = denied.json()
    detail = body.get("detail", body)
    assert detail["error"] == "FORBIDDEN"

    ok = client.get("/api/v1/admin/keys", headers={"X-API-Key": admin_secret})
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["count"] >= 2
    labels = {item["label"] for item in payload["keys"]}
    assert "Admin key" in labels
    assert "Analyst key" in labels


def test_revoked_key_returns_401_immediately(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "revoked.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")

    app_db = build_app_database_components(Settings(_env_file=None))  # type: ignore[arg-type,call-arg]
    created = app_db.api_key_store.create(
        CreateApiKeyRequest(label="Revoke me", roles=["analyst"]),
    )
    assert app_db.api_key_store.revoke(key_id=created.api_key.id)

    settings = Settings(
        _env_file=None,  # type: ignore[arg-type,call-arg]
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
    )

    governance = mock_governance_components()
    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch("insightai.main.build_ai_components", return_value=MagicMock()),
        patch("insightai.main.build_database_components", return_value=MagicMock()),
        patch("insightai.main.build_app_database_components", return_value=app_db),
        patch("insightai.main.build_governance_components", return_value=governance),
    ):
        from insightai.main import create_app

        with TestClient(create_app()) as client:
            response = client.post(
                "/api/v1/chat/sessions",
                headers={"X-API-Key": created.secret},
                json={"title": "Should fail"},
            )
            assert response.status_code == 401
