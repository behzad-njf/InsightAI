"""Unit tests for schema context builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.models.schema import SchemaContextRequest
from insightai.infrastructure.schema.context_builder import SchemaContextBuilder
from insightai.infrastructure.schema.markdown_parser import SchemaMarkdownParser
from insightai.infrastructure.schema.registry import SchemaRegistry
from insightai.infrastructure.schema.repository import FileSchemaRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schema" / "database_schema.md"


@pytest.fixture(scope="module")
def schema_registry() -> SchemaRegistry:
    document = SchemaMarkdownParser().parse_file(SCHEMA_PATH)
    return SchemaRegistry(document)


@pytest.fixture(scope="module")
def schema_repository() -> FileSchemaRepository:
    return FileSchemaRepository(SCHEMA_PATH)


def test_children_in_classroom_includes_school_and_accounts(
    schema_registry: SchemaRegistry,
) -> None:
    builder = SchemaContextBuilder(schema_registry)
    result = builder.build(
        SchemaContextRequest(question="How many children are in a classroom?", max_tables=15),
    )
    names = set(result.table_names)
    assert "accounts_user" in names
    assert any(name.startswith("school_") for name in names)
    assert "school_classroomchild" in names or "school_classroom" in names
    assert "Schema context" in result.context_markdown
    assert "accounts_user" in result.context_markdown


def test_repository_build_context(schema_repository: FileSchemaRepository) -> None:
    result = schema_repository.build_context(
        SchemaContextRequest(question="List staff in a school classroom", max_tables=10),
    )
    assert result.table_names
    assert result.context_markdown
