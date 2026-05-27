"""Unit tests for Phase 13.2 explainability builder."""

from __future__ import annotations

from insightai.domain.models.explainability import (
    ExplainabilityBuildRequest,
    ExplainabilityWarning,
    ExplainabilityWarningSeverity,
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
    JoinPatternMetadata,
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
from insightai.infrastructure.explainability.builder import ExplainabilityBuilder


def test_build_sql_path_with_validation_and_schema_context() -> None:
    builder = ExplainabilityBuilder()
    context = SchemaContextResult(
        question="How many orders?",
        tables=[
            SchemaTableContext(
                table=TableMetadata(
                    name="demo_orders",
                    domain="demo",
                    columns=[ColumnMetadata(name="id", data_type="int")],
                ),
                relevance_score=0.8,
                match_reasons=["token index: orders"],
            ),
        ],
        join_patterns=[
            JoinPatternMetadata(
                title="Orders with customers",
                sql="SELECT ... JOIN ...",
            ),
        ],
        context_markdown="## Schema context",
        table_names=["demo_orders"],
    )
    sql_result = SQLGenerationResult(
        sql="SELECT COUNT(*) FROM demo_orders",
        explanation="Count rows.",
        confidence=SQLGenerationConfidence.HIGH,
        generation_source=GenerationSource.TRUSTED_EXAMPLE,
        trusted_asset_id="orders_count",
        trusted_match_confidence=TrustedMatchConfidence.EXACT_SQL,
        tables_used=["demo_orders"],
    )
    validation = SQLValidationResult(
        is_valid=False,
        statement_kind=SQLStatementKind.SELECT,
        violations=["invalid column x"],
        warnings=["implicit cast"],
    )
    payload = builder.build(
        ExplainabilityBuildRequest(
            question="How many orders?",
            route=RouteClassification(
                route=QueryRouteKind.SQL,
                confidence=0.93,
                rationale="structured numeric query",
            ),
            schema_context=context,
            sql_generation=sql_result,
            validation=validation,
            follow_up_questions=["Show by month", "Show by month", "  "],
            sql_executed=True,
        ),
    )
    assert payload.route == QueryRouteKind.SQL
    assert payload.route_confidence == 0.93
    assert payload.referenced_tables == ["demo_orders"]
    assert payload.schema_selection[0].table_name == "demo_orders"
    assert payload.join_pattern_titles == ["Orders with customers"]
    assert payload.generation_source == GenerationSource.TRUSTED_EXAMPLE
    assert payload.trusted is not None
    assert payload.trusted.generation_source == GenerationSource.TRUSTED_EXAMPLE
    assert payload.trusted.trusted_asset_id == "orders_count"
    assert payload.trusted.match_confidence == TrustedMatchConfidence.EXACT_SQL
    assert payload.validation is not None
    assert payload.validation.is_valid is False
    assert len(payload.warnings) == 2
    assert payload.follow_up_questions == ["Show by month"]
    assert payload.sql_executed is True


def test_build_rag_path_infers_route_and_citations() -> None:
    builder = ExplainabilityBuilder()
    retrieval = RAGRetrievalResult(
        question="policy",
        top_k=2,
        sources=[
            RAGSourceCitation(
                id="doc-1",
                source_path="Knowledge/policy.md",
                chunk_index=3,
                text="policy text",
                score=0.77,
                title="Policy",
            ),
        ],
    )
    payload = builder.build(
        ExplainabilityBuildRequest(
            question="What is the leave policy?",
            rag_retrieval=retrieval,
            sql_executed=False,
        ),
    )
    assert payload.route == QueryRouteKind.RAG
    assert payload.rag_citations[0].source_id == "doc-1"
    assert payload.referenced_tables == []
    assert payload.generation_source == GenerationSource.LLM


def test_build_governance_denied_adds_warning_and_sanitizes_message() -> None:
    builder = ExplainabilityBuilder()
    denied = GovernanceDecision(
        sql="",
        applied=True,
        policy=PolicyDecision.deny(
            message="Traceback: ODBC_CONNECT token=secret",
            reason_code="GOVERNANCE_DENIED",
        ),
    )
    payload = builder.build(
        ExplainabilityBuildRequest(
            question="restricted query",
            governance=denied,
            extra_warnings=[
                ExplainabilityWarning(
                    code="PIPELINE",
                    message="stack trace: password leaked",
                    severity=ExplainabilityWarningSeverity.WARNING,
                ),
            ],
        ),
    )
    assert payload.governance is not None
    assert payload.governance.denied is True
    assert payload.governance.policy_ids == ["GOVERNANCE_DENIED"]
    assert payload.warnings
    messages = [w.message for w in payload.warnings]
    assert all("password" not in message.lower() for message in messages)
    assert any(message.startswith("A system warning occurred") for message in messages)


def test_build_governance_allow_with_policy_id() -> None:
    builder = ExplainabilityBuilder()
    allowed = GovernanceDecision(
        sql="SELECT 1",
        applied=True,
        policy=PolicyDecision.allow(
            "SELECT 1",
            dimensions_applied=("campus",),
        ).model_copy(update={"reason_code": "POLICY_SCOPE_CAMPUS"}),
    )
    payload = builder.build(
        ExplainabilityBuildRequest(
            question="count",
            governance=allowed,
        ),
    )
    assert payload.governance is not None
    assert payload.governance.denied is False
    assert payload.governance.policy_reason_code == "POLICY_SCOPE_CAMPUS"
    assert payload.governance.policy_ids == ["POLICY_SCOPE_CAMPUS"]
