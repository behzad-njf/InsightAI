"""Unit tests for SQL generation prompt files and loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.exceptions import PromptNotFoundError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMRole
from insightai.infrastructure.prompts.loader import (
    dialect_label,
    load_sql_generation_prompts,
    render_sql_generation_messages,
    sql_generation_prompts_dir,
)
from tests.conftest import make_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "prompts" / "sql_generation"


def test_prompt_files_exist() -> None:
    assert (PROMPTS_DIR / "system.md").is_file()
    assert (PROMPTS_DIR / "user.md").is_file()


def test_system_prompt_enforces_select_only() -> None:
    bundle = load_sql_generation_prompts()
    system = bundle.render_system(
        sql_dialect=dialect_label(DatabaseKind.MSSQL),
        max_rows=100,
    )
    assert "SELECT" in system
    assert "INSERT" in system or "DELETE" in system
    assert "read-only" in system.lower()
    assert "TOP" in system or "top" in system.lower()
    assert "JSON" in system


def test_user_prompt_renders_placeholders() -> None:
    bundle = load_sql_generation_prompts()
    user = bundle.render_user(
        question="How many children are in a classroom?",
        schema_context="### accounts_user\n- id",
        sql_dialect=dialect_label(DatabaseKind.MSSQL),
        max_rows=500,
    )
    assert "How many children are in a classroom?" in user
    assert "### accounts_user" in user
    assert "Microsoft SQL Server" in user
    assert "500" in user
    assert "{question}" not in user


def test_render_sql_generation_messages() -> None:
    settings = make_settings(sql_max_rows=250)
    messages = render_sql_generation_messages(
        question="List active users",
        schema_context="- accounts_user",
        database_kind=DatabaseKind.MSSQL,
        settings=settings,
    )
    assert len(messages) == 2
    assert messages[0].role == LLMRole.SYSTEM
    assert messages[1].role == LLMRole.USER
    assert "250" in messages[0].content
    assert "List active users" in messages[1].content


def test_load_missing_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_sql_generation_prompts(prompts_dir=Path("/nonexistent/prompts/sql_generation"))


def test_sql_generation_prompts_dir_uses_project_root() -> None:
    settings = make_settings()
    path = sql_generation_prompts_dir(settings)
    assert path == settings.project_root / "prompts" / "sql_generation"
