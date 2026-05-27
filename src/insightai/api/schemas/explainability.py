"""API schemas for explainability payloads (Phase 13.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from insightai.domain.models.ask import AskResult
from insightai.domain.models.explainability import ExplainabilityPayload


class ExplainabilityWarningSchema(BaseModel):
    code: str
    message: str
    severity: str


class SchemaTableSelectionSchema(BaseModel):
    table_name: str
    relevance_score: float
    match_reasons: list[str] = Field(default_factory=list)
    domain: str | None = None


class SchemaTableExclusionSchema(BaseModel):
    table_name: str
    reason: str


class ExplainabilityValidationSchema(BaseModel):
    is_valid: bool
    statement_kind: str | None = None
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_sql_applied: bool = False


class ExplainabilityGovernanceSchema(BaseModel):
    applied: bool = False
    policy_reason_code: str | None = None
    policy_ids: list[str] = Field(default_factory=list)
    dimensions_applied: list[str] = Field(default_factory=list)
    column_masks_applied: list[str] = Field(default_factory=list)
    row_filters_applied: list[str] = Field(default_factory=list)
    denied: bool = False
    deny_message: str | None = None


class ExplainabilityTrustedSchema(BaseModel):
    generation_source: str
    trusted_asset_id: str | None = None
    trusted_asset_kind: str | None = None
    match_confidence: str | None = None


class ExplainabilityCitationSchema(BaseModel):
    citation_index: int
    source_id: str
    source_path: str
    chunk_index: int
    score: float
    title: str | None = None
    section: str | None = None


class ExplainabilitySchema(BaseModel):
    question: str
    route: str
    route_rationale: str = ""
    route_confidence: float | None = None
    referenced_tables: list[str] = Field(default_factory=list)
    schema_selection: list[SchemaTableSelectionSchema] = Field(default_factory=list)
    excluded_tables: list[SchemaTableExclusionSchema] = Field(default_factory=list)
    schema_selection_reasons: dict[str, list[str]] = Field(default_factory=dict)
    join_pattern_titles: list[str] = Field(default_factory=list)
    generation_source: str
    trusted: ExplainabilityTrustedSchema | None = None
    validation: ExplainabilityValidationSchema | None = None
    governance: ExplainabilityGovernanceSchema | None = None
    warnings: list[ExplainabilityWarningSchema] = Field(default_factory=list)
    rag_citations: list[ExplainabilityCitationSchema] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    dry_run: bool = False
    sql_executed: bool = False

    @classmethod
    def from_domain_payload(cls, payload: ExplainabilityPayload) -> ExplainabilitySchema:
        return cls.model_validate(payload.model_dump(mode="json"))

    @classmethod
    def from_ask_result(cls, result: AskResult) -> ExplainabilitySchema | None:
        if result.explainability is None:
            return None
        return cls.from_domain_payload(result.explainability)
