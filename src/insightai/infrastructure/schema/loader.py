"""Load schema repository from configured markdown path."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from insightai.domain.exceptions import SchemaNotFoundError
from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.schema.repository import FileSchemaRepository


def resolve_schema_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    path = settings.schema_markdown_absolute
    if not path.is_file():
        msg = f"Schema markdown not found: {path}"
        raise SchemaNotFoundError(msg)
    return path


@lru_cache
def get_schema_repository(_cache_key: str | None = None) -> ISchemaRepository:
    """
    Cached schema repository singleton.

    Pass unique `_cache_key` only in tests after env changes; normally call with no args.
    """
    settings = get_settings()
    path = resolve_schema_path(settings)
    return FileSchemaRepository(path)


def clear_schema_repository_cache() -> None:
    """Clear cached repository (tests)."""
    get_schema_repository.cache_clear()
