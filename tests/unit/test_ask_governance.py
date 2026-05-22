"""Ask pipeline governance hook (Phase 12.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from insightai.application.use_cases.ask import AskUseCase
from insightai.domain.models.api_key import ApiKey
from insightai.domain.models.ask import AskRequest
from insightai.domain.models.auth import AuthenticatedPrincipal
from insightai.domain.models.governance import GovernanceContext, GovernanceDecision
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.sql_generation import (
    GenerateSQLResult,
    SQLGenerationConfidence,
    SQLGenerationResult,
)


class RecordingEnforcer:
    def __init__(self) -> None:
        self.last_context: GovernanceContext | None = None

    def enforce(self, sql: str, context: GovernanceContext | None) -> GovernanceDecision:
        self.last_context = context
        return GovernanceDecision(sql=sql, applied=False)


def _sql_result() -> GenerateSQLResult:
    return GenerateSQLResult(
        question="count",
        sql=SQLGenerationResult(
            sql="SELECT 1 AS n",
            explanation="test",
            tables_used=[],
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


def test_prepare_governed_sql_passes_governance_context() -> None:
    enforcer = RecordingEnforcer()
    principal = AuthenticatedPrincipal.from_api_key(
        ApiKey(
            id="00000000-0000-0000-0000-000000000011",
            key_prefix="prefix123456",
            label="Gov test",
            roles=["analyst"],
            attributes={"campus_ids": ["1"]},
            created_at=datetime.now(UTC),
        ),
    )
    gov = GovernanceContext.from_authenticated_principal(principal)
    assert gov is not None

    use_case = AskUseCase(MagicMock(), MagicMock(), MagicMock(), governance=enforcer)
    request = AskRequest(question="count", governance_context=gov)
    preparation = use_case._prepare_governed_sql(request, _sql_result())

    assert enforcer.last_context is not None
    assert enforcer.last_context.attribute_values("campus_ids") == ("1",)
    assert preparation.validated_sql == "SELECT 1 AS n"
