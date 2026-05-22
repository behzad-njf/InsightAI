"""Alembic migration tests for the platform app database (Phase 16.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from insightai.infrastructure.config.settings import Settings, clear_settings_cache


def _alembic_config_for(root: Path, db_url: str) -> Config:
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(root / "src"))
    cfg.attributes["sqlalchemy.url"] = db_url
    return cfg


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_app_db_upgrade_head_sqlite(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "test_app.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()

    settings = Settings(_env_file=None)  # type: ignore[arg-type,call-arg]
    assert settings.resolved_app_database_url() == db_url

    cfg = _alembic_config_for(project_root, db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).one()
    assert row[0] == "002_api_keys"
