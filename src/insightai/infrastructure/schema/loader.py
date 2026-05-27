"""Load schema repository from configured JSON and/or markdown paths."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.schema.repository import FileSchemaRepository
from insightai.infrastructure.schema.schema_loader import resolve_schema_cache_path


def resolve_schema_path(settings: Settings | None = None) -> Path:
    """Primary schema file path (JSON when auto/json, else markdown) for cache keys and logging."""
    return resolve_schema_cache_path(settings)


@lru_cache
def get_schema_repository(_cache_key: str | None = None) -> ISchemaRepository:
    """
    Cached schema repository singleton.

    Pass unique `_cache_key` only in tests after env changes; normally call with no args.
    """
    settings = get_settings()
    return FileSchemaRepository(settings=settings)


def clear_schema_repository_cache() -> None:
    """Clear cached repository (tests)."""
    get_schema_repository.cache_clear()
