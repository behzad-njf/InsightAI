"""Parse django-db-schema-doc ``schema.json`` exports into SchemaDocument."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from insightai.domain.models.schema import (
    ColumnMetadata,
    DomainMetadata,
    ForeignKeyMetadata,
    JoinPatternMetadata,
    QueryExampleMetadata,
    SchemaDocument,
    TableMetadata,
)
from insightai.infrastructure.schema.domain_infer import infer_domain

SCHEMA_VERSION = 1


class SchemaJsonParser:
    """Load ``export_schema_json`` output (schema_version 1)."""

    def parse_file(self, path: Path) -> SchemaDocument:
        data = json.loads(path.read_text(encoding="utf-8"))
        return self.parse_dict(data, source_path=str(path))

    def parse_dict(self, data: dict[str, Any], *, source_path: str = "<memory>") -> SchemaDocument:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            msg = f"Unsupported schema_version {version!r}; expected {SCHEMA_VERSION}."
            raise ValueError(msg)

        tables = [self._parse_table(entry) for entry in data.get("tables") or []]
        tables.sort(key=lambda table: table.name)
        hub_names, hub_meta = self._hub_metadata(tables)
        tables = [_apply_hub_metadata(table, hub_meta) for table in tables]

        domains = self._domains_from_tables(tables)
        join_patterns = join_patterns_from_tables(tables)

        return SchemaDocument(
            source_path=source_path,
            format="django_db_schema_doc_json",
            domains=domains,
            tables=tables,
            join_patterns=join_patterns,
            hub_table_names=hub_names,
        )

    def merge_examples_file(
        self,
        document: SchemaDocument,
        examples_path: Path,
    ) -> SchemaDocument:
        """Attach examples from ``export_schema_examples`` when not in schema.json."""
        data = json.loads(examples_path.read_text(encoding="utf-8"))
        if data.get("examples_version") != 1:
            msg = f"Unsupported examples_version {data.get('examples_version')!r}"
            raise ValueError(msg)

        by_table = {entry["table"]: entry for entry in data.get("tables") or []}
        updated_tables: list[TableMetadata] = []
        for table in document.tables:
            entry = by_table.get(table.name)
            if entry is None or table.query_examples:
                updated_tables.append(table)
                continue
            examples = [_parse_example(item) for item in entry.get("examples") or []]
            updated_tables.append(
                table.model_copy(update={"query_examples": examples}),
            )

        return document.model_copy(
            update={
                "tables": updated_tables,
                "join_patterns": join_patterns_from_tables(updated_tables),
            },
        )

    def _parse_table(self, entry: dict[str, Any]) -> TableMetadata:
        name = str(entry["name"])
        schema_name = str(entry.get("schema") or "dbo")
        pk_parts = entry.get("primary_key") or []
        primary_key = ", ".join(str(part) for part in pk_parts) if pk_parts else None

        django_model: str | None = None
        description: str | None = None
        dm = entry.get("django_model")
        if isinstance(dm, dict):
            app_label = dm.get("app_label", "")
            model_name = dm.get("model_name", "")
            if app_label and model_name:
                django_model = f"{app_label}.{model_name}"
            description = (dm.get("doc") or "").strip() or None
        business = entry.get("business")
        if isinstance(business, dict):
            biz_desc = (business.get("description") or "").strip()
            if biz_desc and not description:
                description = biz_desc

        columns = [_parse_column(column) for column in entry.get("columns") or []]
        foreign_keys = [
            ForeignKeyMetadata(
                column=str(fk["from_column"]),
                parent_table=str(fk["to_table"]),
                parent_column=str(fk["to_column"]),
                on_delete=(fk.get("on_delete") or None) or None,
                on_update=(fk.get("on_update") or None) or None,
            )
            for fk in entry.get("outgoing_fks") or []
        ]
        query_examples = [_parse_example(item) for item in entry.get("query_examples") or []]

        return TableMetadata(
            name=name,
            schema_name=schema_name,
            domain=infer_domain(name),
            primary_key=primary_key,
            description=description,
            django_model=django_model,
            columns=columns,
            foreign_keys=foreign_keys,
            query_examples=query_examples,
            approx_row_count=entry.get("row_count"),
        )

    @staticmethod
    def _hub_metadata(
        tables: list[TableMetadata],
    ) -> tuple[list[str], dict[str, dict[str, object]]]:
        in_degree: dict[str, int] = defaultdict(int)
        for table in tables:
            for fk in table.foreign_keys:
                in_degree[fk.parent_table.lower()] += 1

        ranked = sorted(in_degree.items(), key=lambda item: (-item[1], item[0]))
        hub_names = [name for name, _ in ranked[:25]]
        row_by_name = {table.name.lower(): table.approx_row_count for table in tables}
        hub_meta = {
            name: {
                "incoming_fk_count": count,
                "approx_row_count": row_by_name.get(name),
            }
            for name, count in ranked[:25]
        }
        return hub_names, hub_meta

    @staticmethod
    def _domains_from_tables(tables: list[TableMetadata]) -> list[DomainMetadata]:
        counts: dict[str, int] = defaultdict(int)
        for table in tables:
            counts[table.domain or "other"] += 1
        return [
            DomainMetadata(name=domain, table_count=count)
            for domain, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]


def _parse_column(entry: dict[str, Any]) -> ColumnMetadata:
    return ColumnMetadata(
        name=str(entry["name"]),
        data_type=str(entry.get("type_display") or ""),
        nullable=bool(entry.get("nullable")),
        is_primary_key=bool(entry.get("is_primary_key")),
        default=entry.get("default"),
        ordinal=entry.get("ordinal"),
    )


def _parse_example(entry: dict[str, Any]) -> QueryExampleMetadata:
    return QueryExampleMetadata(
        kind=str(entry.get("kind") or "sql"),
        title=str(entry.get("title") or ""),
        code=str(entry.get("code") or "").strip(),
        related_tables=[str(name) for name in entry.get("related_tables") or []],
    )


def _apply_hub_metadata(
    table: TableMetadata,
    hub_meta: dict[str, dict[str, object]],
) -> TableMetadata:
    meta = hub_meta.get(table.name.lower())
    if not meta:
        return table
    return table.model_copy(
        update={
            "incoming_fk_count": meta["incoming_fk_count"],
            "approx_row_count": meta.get("approx_row_count"),
            "is_hub": True,
        },
    )


def join_patterns_from_tables(tables: list[TableMetadata]) -> list[JoinPatternMetadata]:
    """Derive join SQL snippets from per-table query examples."""
    patterns: list[JoinPatternMetadata] = []
    seen_sql: set[str] = set()
    for table in tables:
        for example in table.query_examples:
            if example.kind != "sql":
                continue
            if "join" not in example.title.lower() and not example.related_tables:
                continue
            key = example.code.strip()
            if not key or key in seen_sql:
                continue
            seen_sql.add(key)
            patterns.append(
                JoinPatternMetadata(
                    title=f"{table.name}: {example.title}",
                    sql=key,
                ),
            )
    return patterns
