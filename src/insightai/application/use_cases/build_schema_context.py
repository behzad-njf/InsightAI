"""Build schema context for SQL generation prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.infrastructure.observability.tracing import set_span_attributes, start_span

if TYPE_CHECKING:
    from insightai.domain.ports.schema_repository import ISchemaRepository


class BuildSchemaContextUseCase:
    """Retrieve relevant schema metadata for a user question."""

    def __init__(self, schema_repository: ISchemaRepository) -> None:
        self._repository = schema_repository

    def execute(self, request: SchemaContextRequest) -> SchemaContextResult:
        with start_span(
            "insightai.schema.context",
            attributes={"insightai.schema.max_tables": request.max_tables},
        ):
            result = self._repository.build_context(request)
            set_span_attributes(
                {"insightai.schema.table_count": len(result.table_names)},
            )
        return result
