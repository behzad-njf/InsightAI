"""SQLAlchemy engine factory for the platform app database."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from insightai.infrastructure.config.database_url import normalize_sqlalchemy_url
from insightai.infrastructure.database.dialect import infer_kind_from_url

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.infrastructure.config.settings import Settings


def ensure_sqlite_parent_dir(url: str) -> None:
    """Create parent directory for file-based SQLite URLs."""
    if not url.lower().startswith("sqlite:"):
        return
    if ":memory:" in url:
        return
    # sqlite:////absolute/path or sqlite:///relative/path
    path_part = url.split("sqlite:///", 1)[-1]
    if path_part.startswith("/"):
        db_path = Path(path_part)
    else:
        db_path = Path(path_part)
    if db_path.suffix in {".db", ".sqlite", ".sqlite3"}:
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_app_database_engine(settings: Settings) -> Engine:
    """Build an engine for ``settings.resolved_app_database_url()``."""
    url = normalize_sqlalchemy_url(settings.resolved_app_database_url())
    ensure_sqlite_parent_dir(url)
    kind = infer_kind_from_url(url)
    engine_kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "echo": settings.debug,
    }
    if kind and kind.value == "sqlite":
        if ":memory:" in url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = StaticPool
    return create_engine(url, **engine_kwargs)
