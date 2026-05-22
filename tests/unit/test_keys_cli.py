"""CLI tests for insightai-keys (Phase 16.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from insightai.cli.keys import main as keys_main
from insightai.infrastructure.config.settings import clear_settings_cache


@pytest.fixture
def keys_db(project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "cli_keys.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", db_url)
    clear_settings_cache()
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")
    return db_file


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_keys_create_and_list(keys_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = keys_main(
        [
            "create",
            "--label",
            "CLI test integration",
            "--roles",
            "analyst",
            "--attributes",
            '{"campus_ids":["1"]}',
        ],
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "iai_" in out
    assert "save the secret" in out.lower() or "cannot be shown" in out.lower()

    capsys.readouterr()
    code = keys_main(["list"])
    assert code == 0
    listed = capsys.readouterr().out
    assert "CLI test integration" in listed
    assert "prefix=" in listed
