"""Trusted semantic layer domain models (Phase 11).

Approved metrics and example queries live in instance YAML under ``config/semantic/``.
SQL generation can match these assets before calling an LLM and label answers with
``GenerationSource`` for clients and audit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator

from insightai.domain.models.database import DatabaseKind


class GenerationSource(StrEnum):
    """How the final read-only SQL was produced."""

    LLM = "llm"
    TRUSTED_METRIC = "trusted_metric"
    TRUSTED_EXAMPLE = "trusted_example"
    RULE_TEMPLATE = "rule_template"


class TrustedAssetKind(StrEnum):
    """Kind of approved semantic asset."""

    METRIC = "metric"
    EXAMPLE_QUERY = "example_query"


class TrustedMatchConfidence(StrEnum):
    """Confidence tier for a trusted SQL match (not LLM self-report)."""

    EXACT_SQL = "exact_sql"
    NORMALIZED_SQL = "normalized_sql"
    QUESTION_MATCH = "question_match"
    NONE = "none"


class TrustedMetric(BaseModel):
    """Organization-approved metric definition with canonical SQL."""

    id: str = Field(min_length=1, description="Stable id, e.g. active_student_count.")
    title: str = Field(min_length=1, description="Human label for analysts.")
    sql: str = Field(min_length=1, description="Read-only SQL template or full query.")
    description: str = Field(default="", description="When to use this metric.")
    question_hints: list[str] = Field(
        default_factory=list,
        description="Optional NL phrases that map to this metric (rule path, not fuzzy LLM).",
    )
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    dialect: DatabaseKind | None = Field(
        default=None,
        description="Optional dialect override; instance default when None.",
    )

    model_config = {"frozen": True}

    @field_validator("id", "title", mode="before")
    @classmethod
    def strip_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("sql", mode="after")
    @classmethod
    def sql_non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "sql must not be empty"
            raise ValueError(msg)
        return value.strip()


class ExampleQuery(BaseModel):
    """Approved question → SQL pair (golden example)."""

    id: str = Field(min_length=1, description="Stable id, e.g. kids_in_classroom_abc.")
    question: str = Field(
        min_length=1,
        description="Canonical natural-language question.",
    )
    sql: str = Field(min_length=1, description="Approved read-only SQL.")
    description: str = Field(default="", description="Notes for operators.")
    question_aliases: list[str] = Field(
        default_factory=list,
        description="Alternate phrasings that should resolve to this example.",
    )
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    dialect: DatabaseKind | None = None

    model_config = {"frozen": True}

    @field_validator("id", "question", mode="before")
    @classmethod
    def strip_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("sql", mode="after")
    @classmethod
    def sql_non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "sql must not be empty"
            raise ValueError(msg)
        return value.strip()

    def all_question_phrases(self) -> list[str]:
        """Canonical question plus aliases (deduped, normalized for matching)."""
        seen: set[str] = set()
        phrases: list[str] = []
        for raw in (self.question, *self.question_aliases):
            normalized = _normalize_question_phrase(raw)
            if normalized and normalized not in seen:
                seen.add(normalized)
                phrases.append(normalized)
        return phrases


def _normalize_question_phrase(text: str) -> str:
    """Shared NL phrase normalization (also used by infrastructure matcher)."""
    collapsed = " ".join(text.strip().lower().split())
    return collapsed.rstrip("?.!")


class SemanticCatalog(BaseModel):
    """Loaded trusted assets for one deployment instance."""

    metrics: list[TrustedMetric] = Field(default_factory=list)
    example_queries: list[ExampleQuery] = Field(default_factory=list)
    source_paths: list[str] = Field(
        default_factory=list,
        description="YAML paths loaded (audit/debug).",
    )

    model_config = {"frozen": True}

    @property
    def enabled_metrics(self) -> list[TrustedMetric]:
        return [m for m in self.metrics if m.enabled]

    @property
    def enabled_example_queries(self) -> list[ExampleQuery]:
        return [q for q in self.example_queries if q.enabled]


class TrustedSQLMatchRequest(BaseModel):
    """Input for matching a question or SQL string against the semantic catalog."""

    question: str = Field(min_length=1)
    sql: str | None = Field(
        default=None,
        description="When set, try normalized/exact SQL match before question rules.",
    )
    database_kind: DatabaseKind = DatabaseKind.MSSQL

    model_config = {"frozen": True}


class TrustedSQLMatchResult(BaseModel):
    """Outcome of trusted matching (no LLM)."""

    matched: bool = False
    generation_source: GenerationSource = GenerationSource.LLM
    asset_kind: TrustedAssetKind | None = None
    asset_id: str | None = None
    asset_title: str | None = None
    confidence: TrustedMatchConfidence = TrustedMatchConfidence.NONE
    sql: str = ""
    explanation: str = ""

    model_config = {"frozen": True}

    @property
    def trusted_asset_id(self) -> str | None:
        """Alias for API field ``trusted_asset_id`` (Phase 11.7)."""
        return self.asset_id

    @classmethod
    def no_match(cls) -> Self:
        return cls(matched=False)

    @classmethod
    def from_metric(
        cls,
        metric: TrustedMetric,
        *,
        confidence: TrustedMatchConfidence,
        explanation: str | None = None,
    ) -> Self:
        return cls(
            matched=True,
            generation_source=GenerationSource.TRUSTED_METRIC,
            asset_kind=TrustedAssetKind.METRIC,
            asset_id=metric.id,
            asset_title=metric.title,
            confidence=confidence,
            sql=metric.sql,
            explanation=explanation or metric.description or metric.title,
        )

    @classmethod
    def from_example(
        cls,
        example: ExampleQuery,
        *,
        confidence: TrustedMatchConfidence,
        explanation: str | None = None,
    ) -> Self:
        return cls(
            matched=True,
            generation_source=GenerationSource.TRUSTED_EXAMPLE,
            asset_kind=TrustedAssetKind.EXAMPLE_QUERY,
            asset_id=example.id,
            asset_title=example.question,
            confidence=confidence,
            sql=example.sql,
            explanation=explanation or example.description or example.question,
        )
