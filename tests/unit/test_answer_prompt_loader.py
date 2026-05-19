"""Unit tests for answer generation prompt files and loader (Phase 6.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from insightai.domain.exceptions import PromptNotFoundError
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.llm import LLMRole
from insightai.infrastructure.prompts.loader import (
    answer_generation_prompts_dir,
    load_answer_generation_prompts,
    load_answer_generation_stream_prompts,
    render_answer_generation_messages,
    render_answer_generation_stream_messages,
)
from insightai.infrastructure.prompts.result_format import format_query_result_for_prompt
from tests.conftest import make_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "prompts" / "answer_generation"


def test_answer_prompt_files_exist() -> None:
    assert (PROMPTS_DIR / "system.md").is_file()
    assert (PROMPTS_DIR / "user.md").is_file()
    assert (PROMPTS_DIR / "stream_system.md").is_file()
    assert (PROMPTS_DIR / "stream_user.md").is_file()


def test_system_prompt_forbids_hallucinated_numbers() -> None:
    bundle = load_answer_generation_prompts()
    system = bundle.render_system()
    lower = system.lower()
    assert "do not invent" in lower or "not invent" in lower
    assert "row count" in lower or "row_count" in lower
    assert "JSON" in system


def test_user_prompt_renders_placeholders() -> None:
    bundle = load_answer_generation_prompts()
    user = bundle.render_user(
        question="How many children per classroom?",
        sql="SELECT id, COUNT(*) AS n FROM school_classroomchild GROUP BY id",
        row_count=2,
        truncated=True,
        column_names="id, n",
        result_table="| id | n |\n| --- | --- |\n| 10 | 2 |",
    )
    assert "How many children per classroom?" in user
    assert "SELECT id, COUNT(*)" in user
    assert "Row count:** 2" in user or "**Row count:** 2" in user
    assert "Truncated" in user
    assert "yes" in user
    assert "id, n" in user
    assert "| 10 | 2 |" in user
    assert "{question}" not in user


def test_render_answer_generation_messages() -> None:
    result = QueryResult(
        columns=[
            QueryColumn(name="classroom_id"),
            QueryColumn(name="child_count"),
        ],
        rows=[
            {"classroom_id": 10, "child_count": 2},
            {"classroom_id": 20, "child_count": 1},
        ],
        row_count=2,
        truncated=False,
        execution_time_ms=12.5,
        executed_at=datetime.now(UTC),
    )
    messages = render_answer_generation_messages(
        question="Children per classroom?",
        sql="SELECT classroom_id, COUNT(*) AS child_count FROM enrollments GROUP BY classroom_id",
        query_result=result,
    )
    assert len(messages) == 2
    assert messages[0].role == LLMRole.SYSTEM
    assert messages[1].role == LLMRole.USER
    assert "Children per classroom?" in messages[1].content
    assert "classroom_id" in messages[1].content
    assert "**Row count:** 2" in messages[1].content or "Row count:** 2" in messages[1].content


def test_format_query_result_empty() -> None:
    result = QueryResult(columns=[], rows=[], row_count=0)
    assert format_query_result_for_prompt(result, max_display_rows=50) == "(No rows returned.)"


def test_format_query_result_samples_large_sets() -> None:
    result = QueryResult(
        columns=[QueryColumn(name="id")],
        rows=[{"id": i} for i in range(20)],
        row_count=20,
    )
    table = format_query_result_for_prompt(result, max_display_rows=5)
    assert "Sampled 5 of 20" in table
    assert "| 0 |" in table
    assert "| 19 |" in table


def test_stream_system_prompt_requests_plain_prose() -> None:
    bundle = load_answer_generation_stream_prompts()
    system = bundle.render_system()
    lower = system.lower()
    assert "plain natural language" in lower
    assert "no json" in lower or "not json" in lower or "no json" in system


def test_render_answer_generation_stream_messages_uses_stream_templates() -> None:
    result = QueryResult(
        columns=[QueryColumn(name="id")],
        rows=[{"id": 1}],
        row_count=1,
    )
    messages = render_answer_generation_stream_messages(
        question="Count rows?",
        sql="SELECT COUNT(*) FROM t",
        query_result=result,
    )
    assert "plain natural language" in messages[0].content.lower()
    assert "Return JSON only" not in messages[1].content
    assert "plain natural language" in messages[1].content.lower()


def test_load_missing_answer_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_answer_generation_prompts(
            prompts_dir=Path("/nonexistent/prompts/answer_generation"),
        )


def test_answer_generation_prompts_dir_uses_project_root() -> None:
    settings = make_settings()
    path = answer_generation_prompts_dir(settings)
    assert path == settings.project_root / "prompts" / "answer_generation"
