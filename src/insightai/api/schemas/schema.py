"""API schemas for schema context endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from insightai.domain.models.schema import SchemaContextResult


class SchemaContextQuery(BaseModel):
    question: str = Field(min_length=1)
    max_tables: int = Field(default=12, ge=1, le=50)


class SchemaContextResponse(BaseModel):
    question: str
    table_names: list[str]
    context_markdown: str
    join_pattern_titles: list[str]

    @classmethod
    def from_result(cls, result: SchemaContextResult) -> SchemaContextResponse:
        return cls(
            question=result.question,
            table_names=result.table_names,
            context_markdown=result.context_markdown,
            join_pattern_titles=[pattern.title for pattern in result.join_patterns],
        )
