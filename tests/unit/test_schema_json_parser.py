"""Unit tests for django-db-schema-doc JSON loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from insightai.infrastructure.schema.json_parser import SchemaJsonParser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schema"


def test_merge_examples_file(tmp_path: Path) -> None:
    base = SchemaJsonParser().parse_file(FIXTURES / "django_doc_mini.json")
    table = next(t for t in base.tables if t.name == "demo_orders")
    assert table.query_examples == []

    examples_path = tmp_path / "examples.json"
    examples_path.write_text(
        json.dumps(
            {
                "examples_version": 1,
                "table_count": 1,
                "tables": [
                    {
                        "table": "demo_orders",
                        "django_model": "demo.order",
                        "examples": [
                            {
                                "kind": "sql",
                                "title": "List rows",
                                "code": "SELECT * FROM demo_orders LIMIT 10;",
                                "related_tables": [],
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    merged = SchemaJsonParser().merge_examples_file(base, examples_path)
    orders = next(t for t in merged.tables if t.name == "demo_orders")
    assert len(orders.query_examples) == 1
    assert orders.query_examples[0].title == "List rows"


def test_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        SchemaJsonParser().parse_dict({"schema_version": 99, "tables": []})
