"""Schema repository wiring and startup warm (Phase 9.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.schema.loader import resolve_schema_path
from insightai.infrastructure.schema.repository import FileSchemaRepository

logger = get_logger(__name__)


@dataclass(frozen=True)
class SchemaComponents:
    """Parsed schema held in memory for the process lifetime."""

    repository: ISchemaRepository
    schema_path: Path
    table_count: int
    domain_count: int


def build_schema_components(settings: Settings) -> SchemaComponents:
    """
    Load and parse schema markdown at startup (registry warm).

    Avoids paying parse cost on the first user request.
    """
    path = resolve_schema_path(settings)
    repository = FileSchemaRepository(path)
    document = repository.get_document()
    logger.info(
        "schema_warmed",
        path=str(path),
        table_count=document.table_count,
        domain_count=len(document.domains),
    )
    return SchemaComponents(
        repository=repository,
        schema_path=path,
        table_count=document.table_count,
        domain_count=len(document.domains),
    )
