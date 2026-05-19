"""Schema repository port — load and query parsed schema metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.schema import (
        SchemaContextRequest,
        SchemaContextResult,
        SchemaDocument,
        TableMetadata,
    )


class ISchemaRepository(ABC):
    """Provides access to parsed schema metadata."""

    @abstractmethod
    def get_document(self) -> SchemaDocument:
        """Return the full schema document (cached after first load)."""

    @abstractmethod
    def get_table(self, name: str) -> TableMetadata | None:
        """Lookup table by exact name (case-insensitive)."""

    @abstractmethod
    def list_tables(self) -> list[TableMetadata]:
        """Return all tables."""

    @abstractmethod
    def list_tables_by_domain(self, domain: str) -> list[TableMetadata]:
        """Filter tables by domain prefix or domain field."""

    @abstractmethod
    def list_hub_tables(self) -> list[TableMetadata]:
        """Return hub tables marked in schema doc §2.1."""

    @abstractmethod
    def reload(self) -> SchemaDocument:
        """Force re-parse from source (e.g. after schema file change)."""

    @abstractmethod
    def build_context(self, request: SchemaContextRequest) -> SchemaContextResult:
        """Return relevant schema context for a natural language question."""
