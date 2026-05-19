"""Unit tests for schema markdown parser and registry."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from insightai.infrastructure.schema.markdown_parser import SchemaMarkdownParser
from insightai.infrastructure.schema.registry import SchemaRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schema" / "database_schema.md"


@pytest.fixture(scope="module")
def parsed_schema():
    parser = SchemaMarkdownParser()
    return parser.parse_file(SCHEMA_PATH)


@pytest.fixture(scope="module")
def schema_registry(parsed_schema):
    return SchemaRegistry(parsed_schema)


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_parses_full_document_without_error(parsed_schema) -> None:
    assert len(parsed_schema.tables) >= 200
    assert len(parsed_schema.domains) >= 5
    assert len(parsed_schema.join_patterns) >= 1


def test_parse_runtime_under_five_seconds() -> None:
    parser = SchemaMarkdownParser()
    start = time.perf_counter()
    document = parser.parse_file(SCHEMA_PATH)
    elapsed = time.perf_counter() - start
    assert len(document.tables) >= 200
    assert elapsed < 5.0, f"parse took {elapsed:.2f}s"


def test_accounts_user_hub_metadata(schema_registry: SchemaRegistry) -> None:
    table = schema_registry.get_table("accounts_user")
    assert table is not None
    assert table.is_hub is True
    assert table.incoming_fk_count == 157
    assert table.primary_key == "id"
    assert table.domain == "accounts"
    assert any(column.name == "id" for column in table.columns)


def test_school_classroomchild_columns_and_fks(schema_registry: SchemaRegistry) -> None:
    table = schema_registry.get_table("school_classroomchild")
    assert table is not None
    assert table.domain == "school"
    assert table.primary_key == "id"
    column_names = {column.name for column in table.columns}
    assert column_names == {"id", "child_id", "classroom_id", "term_id"}
    fk_targets = {(fk.column, fk.parent_table) for fk in table.foreign_keys}
    assert ("child_id", "accounts_user") in fk_targets
    assert ("classroom_id", "school_classroom") in fk_targets


def test_hub_tables_include_accounts_user(schema_registry: SchemaRegistry) -> None:
    hub_names = {table.name for table in schema_registry.list_hub_tables()}
    assert "accounts_user" in hub_names
