"""Unit tests for SQL generation post-processing."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.ai.sql_postprocessor import (
    assert_single_statement,
    extract_sql_text,
    postprocess_generated_sql,
)
from insightai.infrastructure.security.sql_readonly import SQLReadOnlyValidator
from tests.conftest import make_settings


def test_extract_sql_from_fence() -> None:
    raw = """```sql
SELECT TOP 5 id FROM accounts_user
```"""
    assert "SELECT TOP 5" in extract_sql_text(raw)


def test_extract_sql_plain() -> None:
    sql = "SELECT id FROM school_classroomchild"
    assert extract_sql_text(sql) == sql


@pytest.fixture
def sqlite_settings():
    return make_settings(database_kind=DatabaseKind.SQLITE)


def test_postprocess_normalizes_whitespace(sqlite_settings) -> None:
    raw = "SELECT   id\nFROM   accounts_user"
    result = postprocess_generated_sql(
        raw,
        enforce_readonly=True,
        database_kind=DatabaseKind.SQLITE,
        settings=sqlite_settings,
    )
    assert result.sql == "SELECT id FROM accounts_user"


def test_postprocess_rejects_multi_statement(sqlite_settings) -> None:
    raw = "SELECT 1; DELETE FROM accounts_user"
    with pytest.raises(SQLGenerationRejectedError) as exc_info:
        postprocess_generated_sql(
            raw,
            database_kind=DatabaseKind.SQLITE,
            settings=sqlite_settings,
        )
    assert "Multiple SQL" in str(exc_info.value)


def test_postprocess_rejects_delete_via_composite_validator(sqlite_settings) -> None:
    with pytest.raises(SQLGenerationRejectedError) as exc_info:
        postprocess_generated_sql(
            "DELETE FROM accounts_user WHERE id = 1",
            database_kind=DatabaseKind.SQLITE,
            settings=sqlite_settings,
        )
    assert exc_info.value.violations
    assert any("DELETE" in violation.upper() for violation in exc_info.value.violations)


def test_postprocess_accepts_with_cte(sqlite_settings) -> None:
    raw = """
    WITH c AS (SELECT id FROM accounts_user)
    SELECT id FROM c
    """
    result = postprocess_generated_sql(
        raw,
        database_kind=DatabaseKind.SQLITE,
        settings=sqlite_settings,
    )
    assert result.sql.upper().startswith("WITH")


def test_postprocess_empty_returns_empty_without_validation() -> None:
    result = postprocess_generated_sql("   ", enforce_readonly=False)
    assert result.sql == ""


def test_assert_single_statement_allows_trailing_semicolon() -> None:
    assert_single_statement("SELECT 1;")
    assert_single_statement("SELECT 1")


def test_fenced_delete_still_rejected(sqlite_settings) -> None:
    raw = "```sql\nDELETE FROM accounts_user\n```"
    with pytest.raises(SQLGenerationRejectedError):
        postprocess_generated_sql(
            raw,
            database_kind=DatabaseKind.SQLITE,
            settings=sqlite_settings,
        )


def test_postprocess_string_delete_accepted_with_composite(sqlite_settings) -> None:
    result = postprocess_generated_sql(
        "SELECT 'DELETE' AS x FROM accounts_user",
        database_kind=DatabaseKind.SQLITE,
        settings=sqlite_settings,
    )
    assert result.sql


def test_postprocess_keyword_only_still_rejects_string_delete() -> None:
    with pytest.raises(SQLGenerationRejectedError):
        postprocess_generated_sql(
            "SELECT 'DELETE' AS x FROM accounts_user",
            validator=SQLReadOnlyValidator(),
            enforce_readonly=True,
        )
