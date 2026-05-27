"""Unit tests for Phase 13 explainability domain models."""

from __future__ import annotations

from insightai.domain.models.explainability import (
    ExplainabilityBuildRequest,
    ExplainabilityGovernanceSummary,
    ExplainabilityPayload,
    ExplainabilityTrustedSource,
    ExplainabilityValidationSummary,
    ExplainabilityWarning,
    ExplainabilityWarningSeverity,
    RAGExplainabilityCitation,
    SchemaTableExclusion,
    SchemaTableSelection,
)
from insightai.domain.models.governance import GovernanceDecision, PolicyDecision
from insightai.domain.models.hybrid import (
    QueryRouteKind,
    RAGRetrievalResult,
    RAGSourceCitation,
    RouteClassification,
)
from insightai.domain.models.schema import (
    ColumnMetadata,
    SchemaContextResult,
    SchemaTableContext,
    TableMetadata,
)
from insightai.domain.models.semantic import GenerationSource, TrustedMatchConfidence
from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.models.sql_generation import (
    SQLGenerationConfidence,
    SQLGenerationResult,
)


def test_explainability_payload_schema_selection_reasons_map() -> None:
    payload = ExplainabilityPayload(
        question="How many students?",
        schema_selection=[
            SchemaTableSelection(
                table_name="dbo.accounts_user",
                relevance_score=0.9,
                match_reasons=["question token: student", "hub table"],
            ),
        ],
    )
    assert payload.schema_selection_reasons == {
        "dbo.accounts_user": ["question token: student", "hub table"],
    }


def test_schema_selection_from_context() -> None:
    table = TableMetadata(
        name="accounts_user",
        domain="accounts",
        columns=[ColumnMetadata(name="id", data_type="int")],
    )
    context = SchemaContextResult(
        question="students",
        tables=[
            SchemaTableContext(
                table=table,
                relevance_score=0.75,
                match_reasons=["keyword match"],
            ),
        ],
        join_patterns=[],
        context_markdown="# schema",
        table_names=["accounts_user"],
    )
    selections = ExplainabilityPayload.schema_selection_from_context(context)
    assert len(selections) == 1
    assert selections[0].table_name == "accounts_user"
    assert selections[0].domain == "accounts"
    assert selections[0].match_reasons == ["keyword match"]


def test_validation_summary_from_result() -> None:
    validation = SQLValidationResult(
        is_valid=True,
        statement_kind=SQLStatementKind.SELECT,
        normalized_sql="SELECT 1",
        warnings=["implicit limit"],
    )
    summary = ExplainabilityValidationSummary.from_validation(validation)
    assert summary.is_valid is True
    assert summary.statement_kind == "select"
    assert summary.normalized_sql_applied is True
    assert summary.warnings == ["implicit limit"]


def test_governance_summary_deny() -> None:
    decision = GovernanceDecision(
        sql="",
        applied=True,
        policy=PolicyDecision.deny(
            message="Campus scope required.",
            reason_code="MISSING_CAMPUS_SCOPE",
        ),
    )
    summary = ExplainabilityGovernanceSummary.from_governance(decision)
    assert summary.denied is True
    assert summary.deny_message == "Campus scope required."
    assert summary.policy_reason_code == "MISSING_CAMPUS_SCOPE"
    assert summary.policy_ids == ["MISSING_CAMPUS_SCOPE"]


def test_trusted_source_from_sql_generation() -> None:
    sql = SQLGenerationResult(
        sql="SELECT COUNT(*) FROM dbo.accounts_user",
        explanation="Count users.",
        confidence=SQLGenerationConfidence.HIGH,
        generation_source=GenerationSource.TRUSTED_METRIC,
        trusted_asset_id="active_student_count",
        trusted_match_confidence=TrustedMatchConfidence.QUESTION_MATCH,
    )
    trusted = ExplainabilityTrustedSource.from_sql_generation(sql)
    assert trusted is not None
    assert trusted.trusted_asset_id == "active_student_count"
    assert trusted.generation_source == GenerationSource.TRUSTED_METRIC


def test_rag_citations_from_retrieval() -> None:
    retrieval = RAGRetrievalResult(
        question="policy",
        top_k=3,
        sources=[
            RAGSourceCitation(
                id="doc-1",
                source_path="Knowledge/policy.md",
                chunk_index=2,
                text="chunk text",
                score=0.88,
                title="Policy",
            ),
        ],
    )
    citations = ExplainabilityPayload.rag_citations_from_retrieval(retrieval)
    assert len(citations) == 1
    assert citations[0].citation_index == 0
    assert citations[0].source_path == "Knowledge/policy.md"
    assert isinstance(citations[0], RAGExplainabilityCitation)


def test_explainability_build_request_carries_route_and_exclusions() -> None:
    request = ExplainabilityBuildRequest(
        question="test",
        route=RouteClassification(
            route=QueryRouteKind.SQL,
            confidence=0.9,
            rationale="numeric question",
        ),
        excluded_tables=[SchemaTableExclusion(table_name="payroll_x", reason="denied pattern")],
    )
    assert request.route is not None
    assert request.route.route == QueryRouteKind.SQL
    assert request.excluded_tables[0].table_name == "payroll_x"
    assert ExplainabilityBuildRequest.model_config.get("frozen") is True


def test_explainability_warning_strips() -> None:
    warning = ExplainabilityWarning(
        code="  SQL_VALIDATION  ",
        message="  Invalid column  ",
        severity=ExplainabilityWarningSeverity.ERROR,
    )
    assert warning.code == "SQL_VALIDATION"
    assert warning.message == "Invalid column"
