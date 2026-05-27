"""Unit tests for schema-driven context builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.models.schema import SchemaContextRequest
from insightai.infrastructure.schema.context_builder import SchemaContextBuilder
from insightai.infrastructure.schema.context_builder_factory import create_schema_context_builder
from insightai.infrastructure.schema.json_parser import SchemaJsonParser
from insightai.infrastructure.schema.registry import SchemaRegistry

from tests.conftest import make_settings

FIXTURE_JSON = Path(__file__).resolve().parents[1] / "fixtures" / "schema" / "django_doc_mini.json"


@pytest.fixture
def demo_registry() -> SchemaRegistry:
    document = SchemaJsonParser().parse_file(FIXTURE_JSON)
    return SchemaRegistry(document)


def test_default_builder_selects_tables_from_schema(demo_registry: SchemaRegistry) -> None:
    builder = SchemaContextBuilder(demo_registry)
    result = builder.build(
        SchemaContextRequest(question="How many demo orders per demo customer?", max_tables=8),
    )
    names = set(result.table_names)
    assert "demo_orders" in names
    assert "demo_customers" in names
    assert "Schema context (read-only)" in result.context_markdown


def test_factory_uses_default_without_plugin(demo_registry: SchemaRegistry) -> None:
    settings = make_settings(schema_context_plugin=None)
    builder = create_schema_context_builder(demo_registry, settings)
    assert type(builder).__name__ == "SchemaContextBuilder"


def test_factory_loads_optional_plugin(demo_registry: SchemaRegistry) -> None:
    plugin_path = Path(__file__).resolve().parents[2] / "context" / "plugins" / "schema_context_extended.py"
    if not plugin_path.is_file():
        pytest.skip("extended plugin not present locally")
    settings = make_settings(
        schema_context_plugin="context.plugins.schema_context_extended:ExtendedSchemaContextBuilder",
    )
    builder = create_schema_context_builder(demo_registry, settings)
    assert type(builder).__name__ == "ExtendedSchemaContextBuilder"
