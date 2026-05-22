"""Unit tests for platform app database settings (Phase 16.1)."""

from __future__ import annotations

from pathlib import Path

from insightai.infrastructure.config.settings import Settings


def test_resolved_app_database_url_default_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)  # type: ignore[arg-type,call-arg]
    url = settings.resolved_app_database_url()
    assert url.startswith("sqlite:///")
    assert "insightai_app.db" in url
    assert (settings.project_root / "data").exists()


def test_resolved_app_database_url_explicit_postgres() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[arg-type,call-arg]
        app_database_url="postgresql+psycopg2://app:secret@db.internal:5432/insightai_app",
    )
    url = settings.resolved_app_database_url()
    assert url.startswith("postgresql+psycopg2://")
    assert "insightai_app" in url
