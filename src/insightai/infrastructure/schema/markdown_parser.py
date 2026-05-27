"""Parse schema markdown (legacy InsightAI or django-db-schema-doc DATABASE.md)."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

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
from insightai.infrastructure.schema.json_parser import join_patterns_from_tables

_TABLE_ANCHOR_RE = re.compile(r'<a id="table-([^"]+)"></a>')
_TABLE_HEADER_RE = re.compile(r"^### `([^`]+)`\s*$")
_META_DOMAIN_RE = re.compile(r"^\-\s+\*\*Domain:\*\*\s+`([^`]+)`")
_META_SCHEMA_RE = re.compile(r"^\-\s+\*\*Schema:\*\*\s+`([^`]+)`")
_META_PK_RE = re.compile(r"^\-\s+\*\*Primary key:\*\*\s+`([^`]+)`")
_META_DJANGO_MODEL_RE = re.compile(r"^\-\s+\*\*Django model:\*\*\s+`([^`]+)`")
_FK_LINE_RE = re.compile(
    r"^-\s+`([^`]+)`\s+→\s+`([^`]+)\.([^`]+)`",
)
_COLUMN_ROW_LEGACY_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`(?:\s*🔑)?\s*\|\s*([^|]+)\|\s*([^|]+)\|",
)
_COLUMN_ROW_DJANGO_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`(?:\s*🔑)?\s*\|"
    r"\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|",
)
_DOMAIN_ROW_LEGACY_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|",
)
_DOMAIN_ROW_DJANGO_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|")
_OUTGOING_FK_HEADERS = (
    "**References (outgoing):**",
    "**References (outgoing foreign keys):**",
)
_INCOMING_FK_HEADERS = (
    "**Referenced by (incoming):**",
    "**Referenced by (incoming foreign keys):**",
)
_HUB_ROW_LEGACY_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*~?([\d,]+)\s*\|\s*(.+?)\s*\|",
)
_HUB_ROW_DJANGO_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|")
_JOIN_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*$")
_SQL_FENCE_RE = re.compile(r"^```sql\s*$", re.IGNORECASE)
_QUERY_EXAMPLE_TITLE_RE = re.compile(r"^-\s*\*(.+?)\*\s*\((SQL|ORM)\)\s*$", re.IGNORECASE)
_DJANGO_DOC_MARKER = "generate_database_doc"


class MarkdownSchemaFormat(StrEnum):
    LEGACY = "legacy_markdown"
    DJANGO_DB_SCHEMA_DOC = "django_db_schema_doc_markdown"


class SchemaMarkdownParser:
    """Parse schema markdown into structured models."""

    def parse_file(self, path: Path) -> SchemaDocument:
        text = path.read_text(encoding="utf-8")
        return self.parse_text(text, source_path=str(path))

    def parse_text(self, text: str, *, source_path: str = "<memory>") -> SchemaDocument:
        fmt = detect_markdown_format(text)
        lines = text.splitlines()
        if fmt == MarkdownSchemaFormat.DJANGO_DB_SCHEMA_DOC:
            return self._parse_django_doc(lines, source_path=source_path)
        return self._parse_legacy(lines, source_path=source_path)

    def _parse_legacy(self, lines: list[str], *, source_path: str) -> SchemaDocument:
        domains = self._parse_domains_legacy(lines)
        hub_info = self._parse_hub_tables_legacy(lines)
        join_patterns = self._parse_join_patterns_legacy(lines)
        tables = self._parse_tables_legacy(lines, hub_info)

        def _hub_fk_count(item: tuple[str, dict[str, object]]) -> int:
            value = item[1].get("incoming_fk_count", 0)
            return value if isinstance(value, int) else 0

        hub_names = [name for name, _ in sorted(hub_info.items(), key=_hub_fk_count, reverse=True)]

        return SchemaDocument(
            source_path=source_path,
            format=MarkdownSchemaFormat.LEGACY.value,
            domains=domains,
            tables=tables,
            join_patterns=join_patterns,
            hub_table_names=hub_names,
        )

    def _parse_django_doc(self, lines: list[str], *, source_path: str) -> SchemaDocument:
        domains = self._parse_domains_django(lines)
        hub_info = self._parse_hub_tables_django(lines)
        tables = self._parse_tables_django(lines, hub_info)

        def _hub_fk_count(item: tuple[str, dict[str, object]]) -> int:
            value = item[1].get("incoming_fk_count", 0)
            return value if isinstance(value, int) else 0

        hub_names = [name for name, _ in sorted(hub_info.items(), key=_hub_fk_count, reverse=True)]
        join_patterns = join_patterns_from_tables(tables)

        return SchemaDocument(
            source_path=source_path,
            format=MarkdownSchemaFormat.DJANGO_DB_SCHEMA_DOC.value,
            domains=domains,
            tables=tables,
            join_patterns=join_patterns,
            hub_table_names=hub_names,
        )

    def _parse_domains_legacy(self, lines: list[str]) -> list[DomainMetadata]:
        domains: list[DomainMetadata] = []
        in_domain_section = False
        for line in lines:
            if line.startswith("## 2. Domain overview"):
                in_domain_section = True
                continue
            if in_domain_section and line.startswith("### "):
                break
            if not in_domain_section:
                continue
            match = _DOMAIN_ROW_LEGACY_RE.match(line.strip())
            if match:
                domains.append(
                    DomainMetadata(
                        name=match.group(1),
                        table_count=int(match.group(2)),
                        description=match.group(3).strip(),
                    )
                )
        return domains

    def _parse_domains_django(self, lines: list[str]) -> list[DomainMetadata]:
        domains: list[DomainMetadata] = []
        in_domain_section = False
        for line in lines:
            if line.startswith("## 3. Domain overview"):
                in_domain_section = True
                continue
            if in_domain_section and line.startswith("## "):
                break
            if not in_domain_section:
                continue
            match = _DOMAIN_ROW_DJANGO_RE.match(line.strip())
            if match:
                domains.append(
                    DomainMetadata(
                        name=match.group(1),
                        table_count=int(match.group(2)),
                    )
                )
        return domains

    def _parse_hub_tables_legacy(self, lines: list[str]) -> dict[str, dict[str, object]]:
        hub: dict[str, dict[str, object]] = {}
        in_hub = False
        for line in lines:
            if "### 2.1 Central hub tables" in line:
                in_hub = True
                continue
            if in_hub and line.startswith("### 2.2"):
                break
            if not in_hub:
                continue
            match = _HUB_ROW_LEGACY_RE.match(line.strip())
            if not match:
                continue
            hub[match.group(1)] = {
                "incoming_fk_count": int(match.group(2)),
                "approx_row_count": int(match.group(3).replace(",", "")),
                "hub_role": match.group(4).strip(),
            }
        return hub

    def _parse_hub_tables_django(self, lines: list[str]) -> dict[str, dict[str, object]]:
        hub: dict[str, dict[str, object]] = {}
        in_hub = False
        for line in lines:
            if line.startswith("## 4. Hub tables"):
                in_hub = True
                continue
            if in_hub and line.startswith("## "):
                break
            if not in_hub:
                continue
            match = _HUB_ROW_DJANGO_RE.match(line.strip())
            if not match:
                continue
            row_raw = match.group(3).strip()
            approx_rows: int | None = None
            if row_raw and row_raw != "—":
                try:
                    approx_rows = int(row_raw.replace(",", ""))
                except ValueError:
                    approx_rows = None
            hub[match.group(1)] = {
                "incoming_fk_count": int(match.group(2)),
                "approx_row_count": approx_rows,
                "hub_role": None,
            }
        return hub

    def _parse_join_patterns_legacy(self, lines: list[str]) -> list[JoinPatternMetadata]:
        patterns: list[JoinPatternMetadata] = []
        in_join_section = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if "### 2.3 Common join patterns" in line:
                in_join_section = True
                i += 1
                continue
            if in_join_section and line.startswith("### 2.4"):
                break
            if not in_join_section:
                i += 1
                continue

            title_match = _JOIN_TITLE_RE.match(line.strip())
            if title_match and i + 1 < len(lines) and _SQL_FENCE_RE.match(lines[i + 1].strip()):
                title = title_match.group(1).strip()
                i += 2
                sql_lines: list[str] = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    sql_lines.append(lines[i])
                    i += 1
                patterns.append(JoinPatternMetadata(title=title, sql="\n".join(sql_lines).strip()))
                i += 1
                continue
            i += 1
        return patterns

    def _parse_tables_legacy(
        self,
        lines: list[str],
        hub_info: dict[str, dict[str, object]],
    ) -> list[TableMetadata]:
        tables: list[TableMetadata] = []
        i = 0
        while i < len(lines):
            anchor = _TABLE_ANCHOR_RE.match(lines[i].strip())
            if anchor:
                table_name = anchor.group(1)
                i += 1
                tables.append(self._parse_table_block_legacy(lines, i, table_name, hub_info))
                i = self._skip_to_next_table(lines, i)
                continue
            i += 1
        return tables

    def _parse_tables_django(
        self,
        lines: list[str],
        hub_info: dict[str, dict[str, object]],
    ) -> list[TableMetadata]:
        tables: list[TableMetadata] = []
        i = 0
        while i < len(lines):
            anchor = _TABLE_ANCHOR_RE.match(lines[i].strip())
            if anchor:
                table_name = anchor.group(1)
                i += 1
                tables.append(self._parse_table_block_django(lines, i, table_name, hub_info))
                i = self._skip_to_next_table(lines, i)
                continue
            i += 1
        return tables

    def _parse_table_block_legacy(
        self,
        lines: list[str],
        start: int,
        table_name: str,
        hub_info: dict[str, dict[str, object]],
    ) -> TableMetadata:
        schema_name = "dbo"
        domain: str | None = None
        primary_key: str | None = None
        columns: list[ColumnMetadata] = []
        foreign_keys: list[ForeignKeyMetadata] = []

        i = start
        if i < len(lines) and _TABLE_HEADER_RE.match(lines[i].strip()):
            i += 1

        in_columns = False
        fk_section: str | None = None
        while i < len(lines):
            line = lines[i]
            if _TABLE_ANCHOR_RE.match(line.strip()):
                break
            if line.startswith("## ") and not line.startswith("###"):
                break

            header_match = _TABLE_HEADER_RE.match(line.strip())
            if header_match and header_match.group(1) != table_name:
                break

            meta_schema = _META_SCHEMA_RE.match(line.strip())
            if meta_schema:
                schema_name = meta_schema.group(1)
                i += 1
                continue

            meta_domain = _META_DOMAIN_RE.match(line.strip())
            if meta_domain:
                domain = meta_domain.group(1)
                i += 1
                continue

            meta_pk = _META_PK_RE.match(line.strip())
            if meta_pk:
                primary_key = meta_pk.group(1)
                i += 1
                continue

            stripped_line = line.strip()
            if stripped_line in (
                "**References (outgoing foreign keys):**",
                "**References (outgoing):**",
            ):
                fk_section = "outgoing"
                in_columns = False
                i += 1
                continue
            if stripped_line in (
                "**Referenced by (incoming foreign keys):**",
                "**Referenced by (incoming):**",
            ):
                fk_section = "incoming"
                in_columns = False
                i += 1
                continue

            if stripped_line == "**Columns:**":
                fk_section = None
                in_columns = True
                i += 1
                continue

            if in_columns and stripped_line.startswith("| ---"):
                i += 1
                continue

            fk_match = _FK_LINE_RE.match(stripped_line)
            if fk_match and fk_section == "outgoing" and not in_columns:
                foreign_keys.append(
                    ForeignKeyMetadata(
                        column=fk_match.group(1),
                        parent_table=fk_match.group(2),
                        parent_column=fk_match.group(3),
                    )
                )
                i += 1
                continue

            if in_columns:
                col_match = _COLUMN_ROW_LEGACY_RE.match(stripped_line)
                if col_match:
                    nullable_raw = col_match.group(4).strip().upper()
                    columns.append(
                        ColumnMetadata(
                            name=col_match.group(2),
                            data_type=col_match.group(3).strip(),
                            nullable=nullable_raw == "YES",
                            is_primary_key="🔑" in line,
                            ordinal=int(col_match.group(1)),
                        )
                    )
                elif not stripped_line.startswith("|"):
                    in_columns = False

            i += 1

        return self._finalize_table(
            table_name,
            schema_name=schema_name,
            domain=domain,
            primary_key=primary_key,
            columns=columns,
            foreign_keys=foreign_keys,
            hub_info=hub_info,
        )

    def _parse_table_block_django(
        self,
        lines: list[str],
        start: int,
        table_name: str,
        hub_info: dict[str, dict[str, object]],
    ) -> TableMetadata:
        schema_name = "dbo"
        domain: str | None = None
        primary_key: str | None = None
        django_model: str | None = None
        description: str | None = None
        columns: list[ColumnMetadata] = []
        foreign_keys: list[ForeignKeyMetadata] = []
        query_examples: list[QueryExampleMetadata] = []

        i = start
        if i < len(lines) and _TABLE_HEADER_RE.match(lines[i].strip()):
            i += 1

        in_columns = False
        fk_section: str | None = None
        in_query_examples = False
        pending_example: dict[str, str] | None = None
        code_fence_lang: str | None = None
        code_lines: list[str] = []

        while i < len(lines):
            line = lines[i]
            if _TABLE_ANCHOR_RE.match(line.strip()):
                break
            if line.startswith("## ") and not line.startswith("###"):
                break

            header_match = _TABLE_HEADER_RE.match(line.strip())
            if header_match and header_match.group(1) != table_name:
                break

            meta_domain = _META_DOMAIN_RE.match(line.strip())
            if meta_domain:
                domain = meta_domain.group(1)
                i += 1
                continue

            django_match = _META_DJANGO_MODEL_RE.match(line.strip())
            if django_match:
                django_model = django_match.group(1)
                i += 1
                continue

            meta_pk = _META_PK_RE.match(line.strip())
            if meta_pk:
                primary_key = meta_pk.group(1)
                i += 1
                continue

            stripped_line = line.strip()
            if stripped_line == "- **Business description (model):**":
                i += 1
                doc_lines: list[str] = []
                while i < len(lines):
                    doc_line = lines[i]
                    if doc_line.strip().startswith("- **") and not doc_line.startswith("  "):
                        break
                    if doc_line.strip() == "" and doc_lines:
                        break
                    if doc_line.startswith("  "):
                        doc_lines.append(doc_line.strip())
                    elif _TABLE_ANCHOR_RE.match(doc_line.strip()) or doc_line.startswith("## "):
                        break
                    i += 1
                if doc_lines:
                    description = " ".join(doc_lines)
                continue

            if stripped_line in _OUTGOING_FK_HEADERS:
                fk_section = "outgoing"
                in_columns = False
                in_query_examples = False
                i += 1
                continue
            if stripped_line in _INCOMING_FK_HEADERS:
                fk_section = "incoming"
                in_columns = False
                in_query_examples = False
                i += 1
                continue

            if stripped_line == "**Columns:**":
                fk_section = None
                in_columns = True
                in_query_examples = False
                i += 1
                continue

            if stripped_line == "**Query examples:**":
                in_query_examples = True
                in_columns = False
                fk_section = None
                i += 1
                continue

            if in_columns and stripped_line.startswith("| ---"):
                i += 1
                continue

            fk_match = _FK_LINE_RE.match(stripped_line)
            if fk_match and fk_section == "outgoing" and not in_columns:
                foreign_keys.append(
                    ForeignKeyMetadata(
                        column=fk_match.group(1),
                        parent_table=fk_match.group(2),
                        parent_column=fk_match.group(3),
                    )
                )
                i += 1
                continue

            if in_columns:
                col_match = _COLUMN_ROW_DJANGO_RE.match(stripped_line)
                if col_match:
                    nullable_raw = col_match.group(7).strip().upper()
                    columns.append(
                        ColumnMetadata(
                            name=col_match.group(2),
                            data_type=col_match.group(6).strip(),
                            nullable=nullable_raw == "YES",
                            is_primary_key="🔑" in line,
                            ordinal=int(col_match.group(1)),
                        )
                    )
                elif not stripped_line.startswith("|"):
                    in_columns = False

            if in_query_examples:
                title_match = _QUERY_EXAMPLE_TITLE_RE.match(stripped_line)
                if title_match:
                    pending_example = {
                        "title": title_match.group(1).strip(),
                        "kind": title_match.group(2).lower(),
                    }
                    i += 1
                    continue
                if pending_example and stripped_line.startswith("```"):
                    code_fence_lang = stripped_line.strip("`").lower() or "sql"
                    code_lines = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        code_lines.append(lines[i])
                        i += 1
                    kind = "orm" if code_fence_lang == "python" else "sql"
                    query_examples.append(
                        QueryExampleMetadata(
                            kind=kind,
                            title=pending_example["title"],
                            code="\n".join(code_lines).strip(),
                        )
                    )
                    pending_example = None
                    code_fence_lang = None
                    i += 1
                    continue

            i += 1

        return self._finalize_table(
            table_name,
            schema_name=schema_name,
            domain=domain,
            primary_key=primary_key,
            description=description,
            django_model=django_model,
            columns=columns,
            foreign_keys=foreign_keys,
            query_examples=query_examples,
            hub_info=hub_info,
        )

    def _finalize_table(
        self,
        table_name: str,
        *,
        schema_name: str,
        domain: str | None,
        primary_key: str | None,
        description: str | None = None,
        django_model: str | None = None,
        columns: list[ColumnMetadata],
        foreign_keys: list[ForeignKeyMetadata],
        query_examples: list[QueryExampleMetadata] | None = None,
        hub_info: dict[str, dict[str, object]],
    ) -> TableMetadata:
        hub = hub_info.get(table_name, {})
        incoming_fk = hub.get("incoming_fk_count")
        approx_rows = hub.get("approx_row_count")
        hub_role = hub.get("hub_role")
        if domain is None:
            domain = infer_domain(table_name)

        return TableMetadata(
            name=table_name,
            schema_name=schema_name,
            domain=domain,
            primary_key=primary_key,
            description=description,
            django_model=django_model,
            columns=columns,
            foreign_keys=foreign_keys,
            query_examples=query_examples or [],
            incoming_fk_count=incoming_fk if isinstance(incoming_fk, int) else None,
            approx_row_count=approx_rows if isinstance(approx_rows, int) else None,
            is_hub=table_name in hub_info,
            hub_role=hub_role if isinstance(hub_role, str) else None,
        )

    @staticmethod
    def _skip_to_next_table(lines: list[str], start: int) -> int:
        i = start
        while i < len(lines):
            if _TABLE_ANCHOR_RE.match(lines[i].strip()):
                return i
            i += 1
        return len(lines)


def detect_markdown_format(text: str) -> MarkdownSchemaFormat:
    if _DJANGO_DOC_MARKER in text or "## 3. Domain overview" in text:
        return MarkdownSchemaFormat.DJANGO_DB_SCHEMA_DOC
    return MarkdownSchemaFormat.LEGACY
