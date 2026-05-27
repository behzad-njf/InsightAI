"""File-backed schema repository implementation."""

from __future__ import annotations

from pathlib import Path

from insightai.domain.models.schema import (
    SchemaContextRequest,
    SchemaContextResult,
    SchemaDocument,
    TableMetadata,
)
from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.schema.context_builder_factory import create_schema_context_builder
from insightai.infrastructure.schema.registry import SchemaRegistry
from insightai.infrastructure.schema.schema_loader import (
    load_schema_document,
    resolve_schema_cache_path,
)

logger = get_logger(__name__)


class FileSchemaRepository(ISchemaRepository):
    """Load schema from django-db-schema-doc JSON and/or markdown on first access."""

    def __init__(
        self,
        schema_path: Path | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._schema_path = schema_path or resolve_schema_cache_path(self._settings)
        self._document: SchemaDocument | None = None
        self._registry: SchemaRegistry | None = None

    def get_document(self) -> SchemaDocument:
        self._ensure_loaded()
        assert self._document is not None
        return self._document

    def get_table(self, name: str) -> TableMetadata | None:
        self._ensure_loaded()
        assert self._registry is not None
        return self._registry.get_table(name)

    def list_tables(self) -> list[TableMetadata]:
        self._ensure_loaded()
        assert self._registry is not None
        return self._registry.list_tables()

    def list_tables_by_domain(self, domain: str) -> list[TableMetadata]:
        self._ensure_loaded()
        assert self._registry is not None
        return self._registry.list_tables_by_domain(domain)

    def list_hub_tables(self) -> list[TableMetadata]:
        self._ensure_loaded()
        assert self._registry is not None
        return self._registry.list_hub_tables()

    def reload(self) -> SchemaDocument:
        self._document = None
        self._registry = None
        return self.get_document()

    def build_context(self, request: SchemaContextRequest) -> SchemaContextResult:
        self._ensure_loaded()
        assert self._registry is not None
        builder = create_schema_context_builder(self._registry, self._settings)
        return builder.build(request)

    def _ensure_loaded(self) -> None:
        if self._document is not None and self._registry is not None:
            return
        document = load_schema_document(self._settings)
        self._document = document
        self._registry = SchemaRegistry(document)
        logger.info(
            "schema_loaded",
            path=str(self._schema_path),
            format=document.format,
            table_count=document.table_count,
            domain_count=len(document.domains),
        )
