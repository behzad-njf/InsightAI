"""In-memory schema registry built from SchemaDocument."""

from __future__ import annotations

from insightai.domain.models.schema import SchemaDocument, TableMetadata


class SchemaRegistry:
    """Indexed lookup over a parsed SchemaDocument."""

    def __init__(self, document: SchemaDocument) -> None:
        self._document = document
        self._tables_by_name: dict[str, TableMetadata] = {
            table.name.lower(): table for table in document.tables
        }
        self._tables_by_domain: dict[str, list[TableMetadata]] = {}
        for table in document.tables:
            domain = (table.domain or "other").lower()
            self._tables_by_domain.setdefault(domain, []).append(table)

    @property
    def document(self) -> SchemaDocument:
        return self._document

    def get_table(self, name: str) -> TableMetadata | None:
        return self._tables_by_name.get(name.lower())

    def list_tables(self) -> list[TableMetadata]:
        return list(self._document.tables)

    def list_tables_by_domain(self, domain: str) -> list[TableMetadata]:
        return list(self._tables_by_domain.get(domain.lower(), []))

    def list_hub_tables(self) -> list[TableMetadata]:
        return [table for table in self._document.tables if table.is_hub]

    def table_names(self) -> list[str]:
        return [table.name for table in self._document.tables]

    def domains(self) -> list[str]:
        return [domain.name for domain in self._document.domains]
