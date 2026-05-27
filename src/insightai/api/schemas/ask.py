"""API schemas for the ask endpoint (Phase 6.5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from insightai.api.schemas.explainability import ExplainabilitySchema
from insightai.api.schemas.llm import TokenUsageSchema
from insightai.domain.models.ask import AskMode, AskResult
from insightai.domain.models.ask import AskRequest as DomainAskRequest
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.hybrid import QueryRouteKind


class AskRequest(BaseModel):
    """Natural language question → SQL → execute → grounded answer."""

    question: str = Field(min_length=1)
    max_context_tables: int = Field(default=12, ge=1, le=50)
    max_rows: int | None = Field(default=None, ge=1, le=100_000)
    database_kind: DatabaseKind | None = None
    sql_model: str | None = None
    sql_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    answer_model: str | None = None
    answer_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_display_rows: int | None = Field(default=None, ge=1, le=500)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    enforce_readonly: bool | None = None
    route: QueryRouteKind | None = None
    mode: AskMode = AskMode.EXECUTE
    use_llm: bool = True

    def to_domain(
        self,
        *,
        governance_context: object | None = None,
    ) -> DomainAskRequest:
        from insightai.domain.models.governance import GovernanceContext

        ctx = governance_context if isinstance(governance_context, GovernanceContext) else None
        return DomainAskRequest(
            question=self.question,
            max_context_tables=self.max_context_tables,
            max_rows=self.max_rows,
            database_kind=self.database_kind,
            sql_model=self.sql_model,
            sql_temperature=self.sql_temperature,
            answer_model=self.answer_model,
            answer_temperature=self.answer_temperature,
            max_display_rows=self.max_display_rows,
            timeout_seconds=self.timeout_seconds,
            enforce_readonly=self.enforce_readonly,
            route=self.route,
            mode=self.mode,
            use_llm=self.use_llm,
            governance_context=ctx,
        )


class AskTimingsSchema(BaseModel):
    route_classification_ms: float = 0.0
    rag_retrieval_ms: float = 0.0
    sql_generation_ms: float
    query_execution_ms: float
    answer_generation_ms: float
    total_ms: float


class AskQueryResultSchema(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float | None = None


class AskResponse(BaseModel):
    """Full pipeline result for debug / internal clients."""

    question: str
    answer: str
    summary_bullets: list[str] = Field(default_factory=list)
    caveats: str | None = None
    row_count: int
    truncation_noted: bool
    sql: str
    sql_explanation: str
    confidence: str
    uncertainty_notes: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    schema_table_names: list[str] = Field(default_factory=list)
    query_result: AskQueryResultSchema
    timings: AskTimingsSchema
    timeout_seconds: int = Field(
        description="Statement timeout applied to query execution.",
    )
    sql_usage: TokenUsageSchema
    answer_usage: TokenUsageSchema
    sql_model: str | None = None
    answer_model: str | None = None
    provider: str | None = None
    route: str = QueryRouteKind.SQL.value
    rag_source_count: int = 0
    citations: list[int] = Field(
        default_factory=list,
        description="1-based document source indices cited in the answer.",
    )
    mode: str = AskMode.EXECUTE.value
    dry_run: bool = False
    generation_source: str = "llm"
    trusted_asset_id: str | None = None
    trusted_match_confidence: str | None = None
    explainability: ExplainabilitySchema | None = Field(
        default=None,
        description="Machine-readable why/trace payload (Phase 13).",
    )

    @classmethod
    def from_domain(cls, result: AskResult) -> AskResponse:
        if result.execution is None or result.sql is None:
            msg = "Ask debug response requires SQL pipeline fields (sql/rag-only not supported)."
            raise ValueError(msg)

        columns = [col.name for col in result.execution.query_result.columns]
        provider = result.answer.answer.provider or result.sql.sql.provider
        return cls(
            question=result.question,
            answer=result.answer.answer.answer,
            summary_bullets=result.answer.answer.summary_bullets,
            caveats=result.answer.answer.caveats,
            row_count=result.execution.query_result.row_count,
            truncation_noted=result.answer.answer.truncation_noted,
            sql=result.execution.sql,
            sql_explanation=result.sql.sql.explanation,
            confidence=result.sql.sql.confidence.value,
            uncertainty_notes=result.sql.sql.uncertainty_notes,
            tables_used=result.sql.sql.tables_used,
            schema_table_names=result.sql.schema_context.table_names,
            query_result=AskQueryResultSchema(
                columns=columns,
                rows=result.execution.query_result.rows,
                row_count=result.execution.query_result.row_count,
                truncated=result.execution.query_result.truncated,
                execution_time_ms=result.execution.query_result.execution_time_ms,
            ),
            timings=AskTimingsSchema(
                route_classification_ms=result.timings.route_classification_ms,
                rag_retrieval_ms=result.timings.rag_retrieval_ms,
                sql_generation_ms=result.timings.sql_generation_ms,
                query_execution_ms=result.timings.query_execution_ms,
                answer_generation_ms=result.timings.answer_generation_ms,
                total_ms=result.timings.total_ms,
            ),
            timeout_seconds=result.execution.execution_options.timeout_seconds,
            sql_usage=TokenUsageSchema(
                prompt_tokens=result.sql.sql.usage.prompt_tokens,
                completion_tokens=result.sql.sql.usage.completion_tokens,
                total_tokens=result.sql.sql.usage.total_tokens,
            ),
            answer_usage=TokenUsageSchema(
                prompt_tokens=result.answer.answer.usage.prompt_tokens,
                completion_tokens=result.answer.answer.usage.completion_tokens,
                total_tokens=result.answer.answer.usage.total_tokens,
            ),
            sql_model=result.sql.sql.model,
            answer_model=result.answer.answer.model,
            provider=provider.value if provider else None,
            route=result.route.value,
            rag_source_count=(
                len(result.rag_retrieval.sources) if result.rag_retrieval is not None else 0
            ),
            citations=list(result.answer.answer.citations),
            mode=AskMode.DRY_RUN.value if result.dry_run else AskMode.EXECUTE.value,
            dry_run=result.dry_run,
            generation_source=result.sql.sql.generation_source.value,
            trusted_asset_id=result.sql.sql.trusted_asset_id,
            trusted_match_confidence=(
                result.sql.sql.trusted_match_confidence.value
                if result.sql.sql.trusted_match_confidence is not None
                else None
            ),
            explainability=ExplainabilitySchema.from_ask_result(result),
        )
