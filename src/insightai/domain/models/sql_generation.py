"""SQL generation domain models — NL question + schema context → read-only SQL."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, TokenUsage
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.semantic import (
    GenerationSource,
    TrustedMatchConfidence,
    TrustedSQLMatchResult,
)


class SQLGenerationConfidence(StrEnum):
    """Model-reported certainty for the generated SQL."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SQLGenerationRequest(BaseModel):
    """
    Input for natural language → SQL generation (Phase 3).

    ``schema_context`` is the markdown block from Phase 2 (``SchemaContextResult``).
    """

    question: str = Field(min_length=1, description="User question in natural language.")
    schema_context: str = Field(
        min_length=1,
        description="Injected schema markdown; authoritative table/column list.",
    )
    database_kind: DatabaseKind = Field(
        default=DatabaseKind.MSSQL,
        description="Target SQL dialect for prompts and validation.",
    )
    schema_table_names: list[str] = Field(
        default_factory=list,
        description="Tables included in context (for auditing and tests).",
    )
    max_rows: int | None = Field(
        default=None,
        ge=1,
        le=100_000,
        description="Row cap for generated SQL; defaults from settings when None.",
    )
    model: str | None = Field(
        default=None,
        description="Optional LLM model override.",
    )
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    domain_context: str | None = Field(
        default=None,
        description="Optional excerpts from Knowledge/ (RAG) for domain-specific SQL rules.",
    )

    model_config = {"frozen": True}

    @classmethod
    def from_schema_context(
        cls,
        *,
        question: str,
        context: SchemaContextResult,
        database_kind: DatabaseKind = DatabaseKind.MSSQL,
        max_rows: int | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        domain_context: str | None = None,
    ) -> Self:
        """Build a request from Phase 2 schema context output."""
        return cls(
            question=question.strip(),
            schema_context=context.context_markdown,
            schema_table_names=list(context.table_names),
            database_kind=database_kind,
            max_rows=max_rows,
            model=model,
            temperature=temperature,
            domain_context=domain_context,
        )


class SQLGenerationLLMOutput(BaseModel):
    """
    Parsed JSON shape from the LLM (see ``prompts/sql_generation/system.md``).

    Used by infrastructure when decoding provider responses (Phase 3.4).
    """

    sql: str = ""
    explanation: str = ""
    confidence: SQLGenerationConfidence = SQLGenerationConfidence.MEDIUM
    uncertainty_notes: str | None = None
    tables_used: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> SQLGenerationConfidence:
        if isinstance(value, SQLGenerationConfidence):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            return SQLGenerationConfidence(normalized)
        msg = f"Invalid confidence value: {value!r}"
        raise ValueError(msg)


class SQLGenerationResult(BaseModel):
    """Outcome of SQL generation — SQL text, explanation, and LLM metadata."""

    sql: str = Field(description="Generated read-only SQL; empty when generation refused.")
    explanation: str = Field(description="Plain-English summary of the query.")
    confidence: SQLGenerationConfidence
    uncertainty_notes: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    schema_table_names: list[str] = Field(
        default_factory=list,
        description="Tables that were available in schema context.",
    )
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model: str | None = None
    provider: LLMProviderKind | None = None
    finish_reason: str | None = None
    generation_source: GenerationSource = Field(
        default=GenerationSource.LLM,
        description="How SQL was produced (Phase 11 trusted semantic layer).",
    )
    trusted_asset_id: str | None = Field(
        default=None,
        description="Matched metric or example_queries id when trusted.",
    )
    trusted_match_confidence: TrustedMatchConfidence | None = Field(
        default=None,
        description="Rule-based match tier when generation_source is trusted.",
    )

    model_config = {"frozen": True}

    @property
    def has_sql(self) -> bool:
        return bool(self.sql.strip())

    @classmethod
    def from_llm_output(
        cls,
        output: SQLGenerationLLMOutput,
        *,
        schema_table_names: list[str] | None = None,
        usage: TokenUsage | None = None,
        model: str | None = None,
        provider: LLMProviderKind | None = None,
        finish_reason: str | None = None,
    ) -> Self:
        """Map parsed LLM JSON into a domain result (Phase 3.3+)."""
        return cls(
            sql=output.sql.strip(),
            explanation=output.explanation.strip(),
            confidence=output.confidence,
            uncertainty_notes=output.uncertainty_notes,
            tables_used=list(output.tables_used),
            schema_table_names=list(schema_table_names or []),
            usage=usage or TokenUsage(),
            model=model,
            provider=provider,
            finish_reason=finish_reason,
        )

    @classmethod
    def from_trusted_match(
        cls,
        match: TrustedSQLMatchResult,
        *,
        schema_table_names: list[str] | None = None,
    ) -> Self:
        """Build SQL generation output from an approved semantic asset (no LLM)."""
        return cls(
            sql=match.sql,
            explanation=match.explanation,
            confidence=_sql_confidence_for_trusted_match(match.confidence),
            schema_table_names=list(schema_table_names or []),
            generation_source=match.generation_source,
            trusted_asset_id=match.trusted_asset_id,
            trusted_match_confidence=match.confidence,
        )

    def with_trusted_sql_verification(self, match: TrustedSQLMatchResult) -> Self:
        """Annotate LLM output when generated SQL matches an approved asset."""
        if not match.matched or match.confidence not in (
            TrustedMatchConfidence.EXACT_SQL,
            TrustedMatchConfidence.NORMALIZED_SQL,
        ):
            return self
        return self.model_copy(
            update={
                "generation_source": match.generation_source,
                "trusted_asset_id": match.trusted_asset_id,
                "trusted_match_confidence": match.confidence,
            },
        )


def _sql_confidence_for_trusted_match(
    confidence: TrustedMatchConfidence,
) -> SQLGenerationConfidence:
    if confidence == TrustedMatchConfidence.QUESTION_MATCH:
        return SQLGenerationConfidence.MEDIUM
    return SQLGenerationConfidence.HIGH


class GenerateSQLRequest(BaseModel):
    """End-to-end NL → SQL request (schema context + generation)."""

    question: str = Field(min_length=1)
    max_context_tables: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Max tables to retrieve in schema context (Phase 2).",
    )
    max_rows: int | None = Field(
        default=None,
        ge=1,
        le=100_000,
        description="Row cap in generated SQL; defaults from settings when None.",
    )
    database_kind: DatabaseKind | None = Field(
        default=None,
        description="SQL dialect override; uses settings.database_kind when unset.",
    )
    model: str | None = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    cache_scope: str | None = Field(
        default=None,
        description="Optional cache namespace (e.g. auth subject) for user-scoped schema caching.",
    )
    use_llm: bool = Field(
        default=True,
        description=(
            "When false and semantic matching finds an asset, skip LLM SQL generation."
        ),
    )

    model_config = {"frozen": True}


class GenerateSQLResult(BaseModel):
    """Schema context retrieval plus SQL generation outcome."""

    question: str
    schema_context: SchemaContextResult
    sql: SQLGenerationResult

    model_config = {"frozen": True}
