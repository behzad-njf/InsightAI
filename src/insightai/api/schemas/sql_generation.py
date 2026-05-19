"""API schemas for SQL generation endpoints (Phase 3.7)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from insightai.api.schemas.llm import TokenUsageSchema
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.sql_generation import GenerateSQLRequest, GenerateSQLResult


class SQLGenerateRequest(BaseModel):
    """Natural language question → schema context → read-only SQL."""

    question: str = Field(min_length=1)
    max_context_tables: int = Field(default=12, ge=1, le=50)
    max_rows: int | None = Field(default=None, ge=1, le=100_000)
    database_kind: DatabaseKind | None = None
    model: str | None = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    def to_domain(self) -> GenerateSQLRequest:
        return GenerateSQLRequest(
            question=self.question,
            max_context_tables=self.max_context_tables,
            max_rows=self.max_rows,
            database_kind=self.database_kind,
            model=self.model,
            temperature=self.temperature,
        )


class SQLGenerateResponse(BaseModel):
    """Generated SQL plus schema context used for the prompt."""

    question: str
    sql: str
    explanation: str
    confidence: str
    uncertainty_notes: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    schema_table_names: list[str] = Field(default_factory=list)
    context_markdown: str
    join_pattern_titles: list[str] = Field(default_factory=list)
    usage: TokenUsageSchema
    model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None

    @classmethod
    def from_domain(cls, result: GenerateSQLResult) -> SQLGenerateResponse:
        return cls(
            question=result.question,
            sql=result.sql.sql,
            explanation=result.sql.explanation,
            confidence=result.sql.confidence.value,
            uncertainty_notes=result.sql.uncertainty_notes,
            tables_used=result.sql.tables_used,
            schema_table_names=result.schema_context.table_names,
            context_markdown=result.schema_context.context_markdown,
            join_pattern_titles=[pattern.title for pattern in result.schema_context.join_patterns],
            usage=TokenUsageSchema(
                prompt_tokens=result.sql.usage.prompt_tokens,
                completion_tokens=result.sql.usage.completion_tokens,
                total_tokens=result.sql.usage.total_tokens,
            ),
            model=result.sql.model,
            provider=result.sql.provider.value if result.sql.provider else None,
            finish_reason=result.sql.finish_reason,
        )
