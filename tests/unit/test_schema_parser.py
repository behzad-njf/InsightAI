"""Unit tests for schema markdown parser and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.infrastructure.config.settings import SchemaSourceKind
from insightai.infrastructure.schema.json_parser import SchemaJsonParser
from insightai.infrastructure.schema.markdown_parser import SchemaMarkdownParser, detect_markdown_format
from insightai.infrastructure.schema.markdown_parser import MarkdownSchemaFormat
from insightai.infrastructure.schema.registry import SchemaRegistry
from insightai.infrastructure.schema.schema_loader import load_schema_document

from tests.conftest import make_settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schema"
DJANGO_JSON = FIXTURES / "django_doc_mini.json"
DJANGO_MD = FIXTURES / "django_doc_mini.md"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SCHEMA_PATH = PROJECT_ROOT / "schema" / "database_schema.md"


@pytest.fixture
def django_json_document():
    return SchemaJsonParser().parse_file(DJANGO_JSON)


@pytest.fixture
def django_md_document():
    return SchemaMarkdownParser().parse_file(DJANGO_MD)


@pytest.fixture
def django_registry(django_json_document):
    return SchemaRegistry(django_json_document)


def test_detect_django_markdown_format() -> None:
    text = DJANGO_MD.read_text(encoding="utf-8")
    assert detect_markdown_format(text) == MarkdownSchemaFormat.DJANGO_DB_SCHEMA_DOC


def test_json_parser_tables_and_join_patterns(django_json_document) -> None:
    assert django_json_document.format == "django_db_schema_doc_json"
    assert len(django_json_document.tables) == 3
    assert len(django_json_document.join_patterns) >= 1
    assert django_json_document.join_patterns[0].sql.startswith("SELECT")


def test_json_parser_hub_and_fks(django_registry: SchemaRegistry) -> None:
    customers = django_registry.get_table("demo_customers")
    assert customers is not None
    assert customers.is_hub is True
    assert customers.incoming_fk_count == 1
    orders = django_registry.get_table("demo_orders")
    assert orders is not None
    assert orders.foreign_keys[0].parent_table == "demo_customers"


def test_django_markdown_parser_matches_json_shape(django_md_document, django_json_document) -> None:
    assert django_md_document.format == "django_db_schema_doc_markdown"
    md_names = {table.name for table in django_md_document.tables}
    json_names = {table.name for table in django_json_document.tables}
    assert md_names == json_names
    md_orders = next(t for t in django_md_document.tables if t.name == "demo_orders")
    assert md_orders.foreign_keys[0].column == "customer_id"
    customers_md = next(t for t in django_md_document.tables if t.name == "demo_customers")
    assert any(example.kind == "sql" for example in customers_md.query_examples)


def test_load_schema_document_prefers_json(tmp_path: Path) -> None:
    json_path = tmp_path / "schema.json"
    json_path.write_text(DJANGO_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    md_path = tmp_path / "database_schema.md"
    md_path.write_text("legacy", encoding="utf-8")

    settings = make_settings(
        schema_source=SchemaSourceKind.AUTO,
        schema_json_path=json_path,
        schema_markdown_path=md_path,
        schema_examples_json_path=tmp_path / "no_examples.json",
    )
    document = load_schema_document(settings)
    assert document.format == "django_db_schema_doc_json"
    assert document.table_count == 3


@pytest.mark.skipif(not LEGACY_SCHEMA_PATH.is_file(), reason="legacy campus schema not in tree")
def test_legacy_campus_schema_still_parses() -> None:
    document = SchemaMarkdownParser().parse_file(LEGACY_SCHEMA_PATH)
    assert document.format == "legacy_markdown"
    assert len(document.tables) >= 200
    assert len(document.join_patterns) >= 1
