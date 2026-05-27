"""Explainability domain models (Phase 13).

Machine-readable transparency for SQL and RAG answers: which tables were selected,
why, how SQL was produced, validation/governance outcomes, and citation alignment.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, computed_field, field_validator

from insightai.domain.models.hybrid import (
    QueryRouteKind,
    RAGRetrievalResult,
    RAGSourceCitation,
    RouteClassification,
)
from insightai.domain.models.semantic import (
    GenerationSource,
    TrustedAssetKind,
    TrustedMatchConfidence,
)

if TYPE_CHECKING:
    from insightai.domain.models.governance import GovernanceDecision
    from insightai.domain.models.schema import SchemaContextResult
    from insightai.domain.models.sql import SQLValidationResult
    from insightai.domain.models.sql_generation import SQLGenerationResult


class ExplainabilityWarningSeverity(StrEnum):
    """Severity for analyst-facing explainability warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ExplainabilityWarning(BaseModel):
    """One sanitized warning (no stack traces or secrets)."""

    code: str = Field(min_length=1, description="Stable machine code, e.g. SQL_VALIDATION.")
    message: str = Field(min_length=1, description="Operator-safe text.")
    severity: ExplainabilityWarningSeverity = ExplainabilityWarningSeverity.WARNING

    model_config = {"frozen": True}

    @field_validator("code", "message", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class SchemaTableSelection(BaseModel):
    """Why a table appeared in schema context for the LLM."""

    table_name: str = Field(min_length=1)
    relevance_score: float = Field(default=0.0, ge=0.0)
    match_reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable selection reasons from schema context builder.",
    )
    domain: str | None = None

    model_config = {"frozen": True}

    @field_validator("table_name", mode="before")
    @classmethod
    def strip_table_name(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            msg = "table_name must be non-empty"
            raise ValueError(msg)
        return text


class SchemaTableExclusion(BaseModel):
    """Table considered but omitted from schema context (sanitized note)."""

    table_name: str = Field(min_length=1)
    reason: str = Field(min_length=1, description="Why the table was not included.")

    model_config = {"frozen": True}

    @field_validator("table_name", "reason", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            msg = "table_name and reason must be non-empty"
            raise ValueError(msg)
        return text


class ExplainabilityValidationSummary(BaseModel):
    """Read-only SQL validation outcome for explainability."""

    is_valid: bool
    statement_kind: str | None = None
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_sql_applied: bool = False

    model_config = {"frozen": True}

    @classmethod
    def from_validation(cls, result: SQLValidationResult) -> Self:
        return cls(
            is_valid=result.is_valid,
            statement_kind=result.statement_kind.value,
            violations=list(result.violations),
            warnings=list(result.warnings),
            normalized_sql_applied=bool(result.normalized_sql),
        )


class ExplainabilityGovernanceSummary(BaseModel):
    """Governance rewrite/deny summary (Phase 12 linkage)."""

    applied: bool = False
    policy_reason_code: str | None = None
    policy_ids: list[str] = Field(
        default_factory=list,
        description="Phase 12 policy identifiers applied/denied for this request.",
    )
    dimensions_applied: list[str] = Field(default_factory=list)
    column_masks_applied: list[str] = Field(default_factory=list)
    row_filters_applied: list[str] = Field(
        default_factory=list,
        description="Serialized row filter descriptions for auditors.",
    )
    denied: bool = False
    deny_message: str | None = None

    model_config = {"frozen": True}

    @classmethod
    def from_governance(cls, decision: GovernanceDecision) -> Self:
        policy = decision.policy
        if policy is None:
            return cls(applied=decision.applied)
        if not policy.allowed:
            return cls(
                applied=True,
                denied=True,
                deny_message=policy.message or "Access denied by data policy.",
                policy_reason_code=policy.reason_code,
                policy_ids=[policy.reason_code] if policy.reason_code else [],
            )
        row_filters = [
            f"{rule.table}.{rule.column} IN ({len(rule.values)} values)"
            for rule in policy.row_filters_applied
        ]
        denied_code = "GOVERNANCE_DENIED"
        return cls(
            applied=decision.applied,
            policy_reason_code=(
                policy.reason_code if policy.reason_code != denied_code else None
            ),
            policy_ids=(
                [policy.reason_code]
                if policy.reason_code and policy.reason_code != "GOVERNANCE_DENIED"
                else []
            ),
            dimensions_applied=list(policy.dimensions_applied or decision.dimensions_applied),
            column_masks_applied=list(policy.column_masks_applied or decision.column_masks_applied),
            row_filters_applied=row_filters,
        )


class ExplainabilityTrustedSource(BaseModel):
    """Trusted semantic layer provenance (Phase 11)."""

    generation_source: GenerationSource
    trusted_asset_id: str | None = None
    trusted_asset_kind: TrustedAssetKind | None = None
    match_confidence: TrustedMatchConfidence | None = None

    model_config = {"frozen": True}

    @classmethod
    def from_sql_generation(cls, result: SQLGenerationResult) -> Self | None:
        if result.generation_source == GenerationSource.LLM and not result.trusted_asset_id:
            return None
        kind: TrustedAssetKind | None = None
        if result.generation_source == GenerationSource.TRUSTED_METRIC:
            kind = TrustedAssetKind.METRIC
        elif result.generation_source == GenerationSource.TRUSTED_EXAMPLE:
            kind = TrustedAssetKind.EXAMPLE_QUERY
        return cls(
            generation_source=result.generation_source,
            trusted_asset_id=result.trusted_asset_id,
            trusted_asset_kind=kind,
            match_confidence=result.trusted_match_confidence,
        )


class RAGExplainabilityCitation(BaseModel):
    """One RAG chunk aligned with answer citations (index matches answer text)."""

    citation_index: int = Field(ge=0, description="0-based index referenced in the answer.")
    source_id: str
    source_path: str
    chunk_index: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    title: str | None = None
    section: str | None = None

    model_config = {"frozen": True}

    @classmethod
    def from_source(cls, index: int, source: RAGSourceCitation) -> Self:
        return cls(
            citation_index=index,
            source_id=source.id,
            source_path=source.source_path,
            chunk_index=source.chunk_index,
            score=source.score,
            title=source.title,
            section=source.section,
        )


class ExplainabilityPayload(BaseModel):
    """
    Machine-readable “why this answer” payload (Phase 13).

    Populated by ``IExplainabilityBuilder`` implementations and returned on ask/chat
    when ``include_explainability`` is enabled.
    """

    question: str = Field(min_length=1)
    route: QueryRouteKind = QueryRouteKind.SQL
    route_rationale: str = ""
    route_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    referenced_tables: list[str] = Field(
        default_factory=list,
        description="Tables referenced in executed or validated SQL.",
    )
    schema_selection: list[SchemaTableSelection] = Field(default_factory=list)
    excluded_tables: list[SchemaTableExclusion] = Field(
        default_factory=list,
        description="Tables scored but omitted (sanitized context_builder notes).",
    )
    join_pattern_titles: list[str] = Field(default_factory=list)
    generation_source: GenerationSource = GenerationSource.LLM
    trusted: ExplainabilityTrustedSource | None = None
    validation: ExplainabilityValidationSummary | None = None
    governance: ExplainabilityGovernanceSummary | None = None
    warnings: list[ExplainabilityWarning] = Field(default_factory=list)
    rag_citations: list[RAGExplainabilityCitation] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    dry_run: bool = False
    sql_executed: bool = False

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def schema_selection_reasons(self) -> dict[str, list[str]]:
        """Per-table selection reasons (API-friendly map)."""
        return {entry.table_name: list(entry.match_reasons) for entry in self.schema_selection}

    @classmethod
    def schema_selection_from_context(
        cls,
        context: SchemaContextResult,
    ) -> list[SchemaTableSelection]:
        return [
            SchemaTableSelection(
                table_name=entry.table.name,
                relevance_score=entry.relevance_score,
                match_reasons=list(entry.match_reasons),
                domain=entry.table.domain,
            )
            for entry in context.tables
        ]

    @classmethod
    def rag_citations_from_retrieval(
        cls,
        retrieval: RAGRetrievalResult,
    ) -> list[RAGExplainabilityCitation]:
        return [
            RAGExplainabilityCitation.from_source(index, source)
            for index, source in enumerate(retrieval.sources)
        ]


class ExplainabilityBuildRequest(BaseModel):
    """Inputs for ``IExplainabilityBuilder.build`` (steps 13.2+)."""

    question: str = Field(min_length=1)
    route: RouteClassification | None = None
    schema_context: SchemaContextResult | None = None
    excluded_tables: list[SchemaTableExclusion] = Field(default_factory=list)
    sql_generation: SQLGenerationResult | None = None
    validation: SQLValidationResult | None = None
    governance: GovernanceDecision | None = None
    rag_retrieval: RAGRetrievalResult | None = None
    referenced_tables: list[str] = Field(
        default_factory=list,
        description="Override when known from validation/SQL parse.",
    )
    extra_warnings: list[ExplainabilityWarning] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    dry_run: bool = False
    sql_executed: bool = False

    model_config = {"frozen": True}
