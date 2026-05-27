"""Phase 12.4 — governed SQL hook (validate → govern → validate)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from insightai.application.pipeline.governed_sql import prepare_governed_sql
from insightai.application.use_cases.ask import AskUseCase
from insightai.domain.exceptions import GovernanceDeniedError, ReadOnlySQLViolationError
from insightai.domain.models.ask import AskRequest
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.governance import GovernanceDecision, Principal
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql import SQLValidationResult
from insightai.domain.models.sql_generation import (
    GenerateSQLResult,
    SQLGenerationConfidence,
    SQLGenerationResult,
)
from insightai.infrastructure.governance.enforcer import SqlGovernanceEnforcer
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

FIXTURE_GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "governance"


class RecordingValidator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def validate(self, sql: str) -> SQLValidationResult:
        self.calls.append(sql.strip())
        return SQLValidationResult(is_valid=True, normalized_sql=sql.strip(), violations=[])


class DenyGovernanceEnforcer:
    def enforce(self, sql: str, context: object | None) -> GovernanceDecision:
        raise GovernanceDeniedError("denied for test")


def _sql_result(sql: str = "SELECT s.id FROM school_school AS s") -> GenerateSQLResult:
    return GenerateSQLResult(
        question="count",
        sql=SQLGenerationResult(
            sql=sql,
            explanation="test",
            confidence=SQLGenerationConfidence.HIGH,
        ),
        schema_context=SchemaContextResult(
            question="count",
            tables=[],
            join_patterns=[],
            context_markdown="",
            table_names=[],
        ),
    )


def test_prepare_validates_before_and_after_governance() -> None:
    catalog = YamlGovernancePolicyLoader(FIXTURE_GOVERNANCE_DIR).load()
    enforcer = SqlGovernanceEnforcer(catalog, database_kind=DatabaseKind.SQLITE)
    validator = RecordingValidator()
    principal = Principal(
        subject="Analyst",
        roles=("analyst",),
        attributes={"campus_ids": ("1",)},
    )

    preparation = prepare_governed_sql(
        _sql_result(),
        governance=enforcer,
        governance_context=principal,
        sql_validator=validator,
        enforce_readonly=True,
    )

    assert len(validator.calls) == 2
    assert validator.calls[0] == validator.calls[1] or preparation.governance_decision.applied
    assert "school_school" in preparation.validated_sql.lower()
    assert preparation.governance_decision.applied


def test_governance_denied_before_post_validation() -> None:
    validator = RecordingValidator()
    with pytest.raises(GovernanceDeniedError):
        prepare_governed_sql(
            _sql_result(),
            governance=DenyGovernanceEnforcer(),
            governance_context=None,
            sql_validator=validator,
            enforce_readonly=True,
        )
    assert len(validator.calls) == 1


def test_pre_validation_rejects_unsafe_sql() -> None:
    class RejectValidator:
        def validate(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                is_valid=False,
                normalized_sql=None,
                violations=["not allowed"],
            )

    with pytest.raises(ReadOnlySQLViolationError):
        prepare_governed_sql(
            _sql_result("DROP TABLE school_school"),
            governance=MagicMock(),
            governance_context=None,
            sql_validator=RejectValidator(),
            enforce_readonly=True,
        )


class RecordingEnforcer:
    def __init__(self) -> None:
        self.called = False

    def enforce(self, sql: str, context: object | None) -> GovernanceDecision:
        self.called = True
        return GovernanceDecision(sql=sql, applied=False)


def test_ask_prepare_governed_sql_invokes_enforcer() -> None:
    enforcer = RecordingEnforcer()
    use_case = AskUseCase(MagicMock(), MagicMock(), MagicMock(), governance=enforcer)
    request = AskRequest(question="count")
    use_case._prepare_governed_sql(request, _sql_result())
    assert enforcer.called is True
