"""Build schema context for SQL generation prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult

if TYPE_CHECKING:
    from insightai.domain.ports.schema_repository import ISchemaRepository


class BuildSchemaContextUseCase:
    """Retrieve relevant schema metadata for a user question."""

    def __init__(self, schema_repository: ISchemaRepository) -> None:
        self._repository = schema_repository

    def execute(self, request: SchemaContextRequest) -> SchemaContextResult:
        return self._repository.build_context(request)
