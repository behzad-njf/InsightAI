"""Unit tests for SQL generation LLM response parsing."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import SQLGenerationParseError
from insightai.domain.models.sql_generation import SQLGenerationConfidence
from insightai.infrastructure.ai.sql_response_parser import (
    extract_json_text,
    parse_sql_generation_llm_output,
)

_SAMPLE_JSON = """{
  "sql": "SELECT TOP 10 id FROM accounts_user",
  "explanation": "Lists user ids.",
  "confidence": "high",
  "uncertainty_notes": null,
  "tables_used": ["accounts_user"]
}"""


def test_extract_json_from_fenced_block() -> None:
    content = f"Here is the query:\n```json\n{_SAMPLE_JSON}\n```"
    assert "SELECT TOP 10" in extract_json_text(content)


def test_extract_json_from_bare_object() -> None:
    assert extract_json_text(_SAMPLE_JSON).startswith("{")


def test_parse_sql_generation_llm_output() -> None:
    output = parse_sql_generation_llm_output(_SAMPLE_JSON)
    assert output.confidence == SQLGenerationConfidence.HIGH
    assert "accounts_user" in output.sql
    assert output.tables_used == ["accounts_user"]


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(SQLGenerationParseError):
        parse_sql_generation_llm_output("not json at all")


def test_parse_empty_content_raises() -> None:
    with pytest.raises(SQLGenerationParseError):
        parse_sql_generation_llm_output("   ")


def test_parse_json_when_sql_field_contains_sql_fence() -> None:
    content = (
        '{"sql": "```sql\\nSELECT TOP 3 id FROM accounts_user\\n```", '
        '"explanation": "ok", "confidence": "high", "tables_used": ["accounts_user"]}'
    )
    output = parse_sql_generation_llm_output(content)
    assert "```" in output.sql
    assert "SELECT TOP 3" in output.sql
