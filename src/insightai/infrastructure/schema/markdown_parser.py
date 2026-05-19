"""Parse schema/database_schema.md into SchemaDocument."""

from __future__ import annotations

import re
from pathlib import Path

from insightai.domain.models.schema import (
    ColumnMetadata,
    DomainMetadata,
    ForeignKeyMetadata,
    JoinPatternMetadata,
    SchemaDocument,
    TableMetadata,
)

_TABLE_ANCHOR_RE = re.compile(r'<a id="table-([^"]+)"></a>')
_TABLE_HEADER_RE = re.compile(r"^### `([^`]+)`\s*$")
_META_SCHEMA_RE = re.compile(r"^\-\s+\*\*Schema:\*\*\s+`([^`]+)`")
_META_DOMAIN_RE = re.compile(r"^\-\s+\*\*Domain:\*\*\s+`([^`]+)`")
_META_PK_RE = re.compile(r"^\-\s+\*\*Primary key:\*\*\s+`([^`]+)`")
_FK_LINE_RE = re.compile(
    r"^-\s+`([^`]+)`\s+→\s+`([^`]+)\.([^`]+)`",
)
_COLUMN_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`(?:\s*🔑)?\s*\|\s*([^|]+)\|\s*([^|]+)\|",
)
_DOMAIN_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|",
)
_HUB_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*~?([\d,]+)\s*\|\s*(.+?)\s*\|",
)
_JOIN_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*$")
_SQL_FENCE_RE = re.compile(r"^```sql\s*$", re.IGNORECASE)


class SchemaMarkdownParser:
    """Parse the CampusMetrics schema markdown reference into structured models."""

    def parse_file(self, path: Path) -> SchemaDocument:
        text = path.read_text(encoding="utf-8")
        return self.parse_text(text, source_path=str(path))

    def parse_text(self, text: str, *, source_path: str = "<memory>") -> SchemaDocument:
        lines = text.splitlines()
        domains = self._parse_domains(lines)
        hub_info = self._parse_hub_tables(lines)
        join_patterns = self._parse_join_patterns(lines)
        tables = self._parse_tables(lines, hub_info)

        def _hub_fk_count(item: tuple[str, dict[str, object]]) -> int:
            value = item[1].get("incoming_fk_count", 0)
            return value if isinstance(value, int) else 0

        hub_names = [name for name, _ in sorted(hub_info.items(), key=_hub_fk_count, reverse=True)]

        return SchemaDocument(
            source_path=source_path,
            domains=domains,
            tables=tables,
            join_patterns=join_patterns,
            hub_table_names=hub_names,
        )

    def _parse_domains(self, lines: list[str]) -> list[DomainMetadata]:
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
            match = _DOMAIN_ROW_RE.match(line.strip())
            if match:
                domains.append(
                    DomainMetadata(
                        name=match.group(1),
                        table_count=int(match.group(2)),
                        description=match.group(3).strip(),
                    )
                )
        return domains

    def _parse_hub_tables(self, lines: list[str]) -> dict[str, dict[str, object]]:
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
            match = _HUB_ROW_RE.match(line.strip())
            if not match:
                continue
            name = match.group(1)
            fk_count = int(match.group(2))
            approx_rows = int(match.group(3).replace(",", ""))
            role = match.group(4).strip()
            hub[name] = {
                "incoming_fk_count": fk_count,
                "approx_row_count": approx_rows,
                "hub_role": role,
            }
        return hub

    def _parse_join_patterns(self, lines: list[str]) -> list[JoinPatternMetadata]:
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

    def _parse_tables(
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
                table = self._parse_table_block(lines, i, table_name, hub_info)
                tables.append(table)
                i = self._skip_to_next_table(lines, i)
                continue
            i += 1
        return tables

    def _parse_table_block(
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
            if stripped_line == "**References (outgoing foreign keys):**":
                fk_section = "outgoing"
                i += 1
                continue
            if stripped_line == "**Referenced by (incoming foreign keys):**":
                fk_section = "incoming"
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
                stripped = line.strip()
                if not stripped:
                    i += 1
                    continue
                col_match = _COLUMN_ROW_RE.match(stripped)
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
                elif not stripped.startswith("|"):
                    in_columns = False

            i += 1

        hub = hub_info.get(table_name, {})
        incoming_fk = hub.get("incoming_fk_count")
        approx_rows = hub.get("approx_row_count")
        hub_role = hub.get("hub_role")
        if domain is None:
            domain = self._infer_domain(table_name)

        return TableMetadata(
            name=table_name,
            schema_name=schema_name,
            domain=domain,
            primary_key=primary_key,
            columns=columns,
            foreign_keys=foreign_keys,
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

    @staticmethod
    def _infer_domain(table_name: str) -> str | None:
        if "_" not in table_name:
            return "other"
        return table_name.split("_", 1)[0]
