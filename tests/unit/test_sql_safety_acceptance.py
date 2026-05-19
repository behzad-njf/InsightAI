"""Phase 4 acceptance tests — composite SQL safety (step 4.4)."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import ReadOnlySQLViolationError, SQLGenerationRejectedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.sql import SQLStatementKind
from insightai.infrastructure.ai.sql_postprocessor import postprocess_generated_sql
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator
from insightai.infrastructure.security.sql_readonly import SQLReadOnlyValidator
from tests.fixtures.sql_safety_payloads import (
    ACCEPTED_PAYLOADS,
    KEYWORD_FALSE_POSITIVE_PAYLOADS,
    REJECTED_PAYLOADS,
    SafetyPayload,
)


def _validator_for(kind: DatabaseKind):
    return create_sql_safety_validator(kind=kind)


@pytest.mark.parametrize("payload", REJECTED_PAYLOADS, ids=lambda p: p.label)
def test_composite_rejects_evil_payloads(payload: SafetyPayload) -> None:
    result = _validator_for(payload.kind).validate(payload.sql)
    assert result.is_valid is False, payload.label
    assert result.statement_kind == SQLStatementKind.FORBIDDEN
    if payload.violation_contains:
        joined = " ".join(result.violations).lower()
        assert any(fragment.lower() in joined for fragment in payload.violation_contains), (
            f"{payload.label}: expected one of {payload.violation_contains} "
            f"in {result.violations}"
        )


@pytest.mark.parametrize("payload", ACCEPTED_PAYLOADS, ids=lambda p: p.label)
def test_composite_accepts_safe_payloads(payload: SafetyPayload) -> None:
    result = _validator_for(payload.kind).validate(payload.sql)
    assert result.is_valid is True, f"{payload.label}: {result.violations}"
    assert result.statement_kind == SQLStatementKind.SELECT
    assert result.normalized_sql is not None
    assert result.normalized_sql.strip()


@pytest.mark.parametrize("payload", KEYWORD_FALSE_POSITIVE_PAYLOADS, ids=lambda p: p.label)
def test_composite_overrides_keyword_false_positives(payload: SafetyPayload) -> None:
    keyword = SQLReadOnlyValidator().validate(payload.sql)
    assert keyword.is_valid is False, "keyword layer should still false-positive"

    composite = _validator_for(payload.kind).validate(payload.sql)
    assert composite.is_valid is True, composite.violations


def test_assert_readonly_includes_reason_code() -> None:
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    with pytest.raises(ReadOnlySQLViolationError) as exc_info:
        validator.assert_readonly("DELETE FROM accounts_user")
    reason = exc_info.value.reason or ""
    assert "forbidden_ast:Delete" in reason or "DELETE" in reason.upper()


@pytest.mark.parametrize(
    "raw_sql",
    [
        "SELECT 1; DELETE FROM accounts_user",
        "SELECT 1;\nDROP TABLE accounts_user",
    ],
    ids=["semicolon_delete", "newline_drop"],
)
def test_postprocessor_rejects_stacked_queries(raw_sql: str) -> None:
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    with pytest.raises(SQLGenerationRejectedError) as exc_info:
        postprocess_generated_sql(raw_sql, validator=validator)
    assert exc_info.value.violations
    message = " ".join(exc_info.value.violations or []).lower()
    assert "multiple" in message or "statement" in message


def test_postprocessor_accepts_fenced_select_with_keywords_in_literals() -> None:
    raw = """```sql
SELECT 'DELETE' AS tag FROM accounts_user
```"""
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    processed = postprocess_generated_sql(raw, validator=validator)
    assert "accounts_user" in processed.sql.lower()
    assert processed.sql.upper().startswith("SELECT")


def test_postprocessor_normalizes_via_ast() -> None:
    sql = "  select   id   from   accounts_user  "
    validator = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    processed = postprocess_generated_sql(sql, validator=validator)
    assert processed.sql == "SELECT id FROM accounts_user"


def test_phase1_reject_cases_all_blocked_by_composite() -> None:
    """Every case from test_sql_readonly rejection paths must stay blocked."""
    phase1_rejects = [
        "DELETE FROM accounts_user WHERE id = 1",
        "INSERT INTO accounts_user (email) VALUES ('a@b.c')",
        "DROP TABLE accounts_user",
        "SELECT * INTO #tmp FROM accounts_user",
        "SELECT 1; SELECT 2",
        "EXEC sp_help",
    ]
    keyword = SQLReadOnlyValidator()
    composite_sqlite = create_sql_safety_validator(kind=DatabaseKind.SQLITE)
    composite_mssql = create_sql_safety_validator(kind=DatabaseKind.MSSQL)

    for sql in phase1_rejects:
        assert keyword.validate(sql).is_valid is False
        composite = composite_mssql if "INTO" in sql or sql.startswith("EXEC") else composite_sqlite
        assert composite.validate(sql).is_valid is False, sql
