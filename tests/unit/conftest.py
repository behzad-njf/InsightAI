"""Unit-test fixtures shared across ``tests/unit/``."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from insightai.infrastructure.app_db.bootstrap import build_app_database_components
from insightai.infrastructure.config.settings import Settings, clear_settings_cache


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def api_key_store(project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "api_keys.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")

    components = build_app_database_components(Settings(_env_file=None))  # type: ignore[arg-type,call-arg]
    return components.api_key_store
