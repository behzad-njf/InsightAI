"""Generate read-only SQL from a natural language question (Phase 3.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.schema import SchemaContextRequest
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    GenerateSQLResult,
    SQLGenerationRequest,
)

if TYPE_CHECKING:
    from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
    from insightai.domain.ports.sql_generator import ISQLGenerator
    from insightai.infrastructure.config.settings import Settings


class GenerateSQLUseCase:
    """
    Orchestrate Phase 2 schema context + Phase 3 SQL generation.

    Flow: question → relevant schema markdown → LLM SQL → post-processed result.
    """

    def __init__(
        self,
        schema_context_use_case: BuildSchemaContextUseCase,
        sql_generator: ISQLGenerator,
        settings: Settings | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._schema_context = schema_context_use_case
        self._sql_generator = sql_generator
        self._settings = settings or get_settings()

    async def execute(self, request: GenerateSQLRequest) -> GenerateSQLResult:
        database_kind = request.database_kind or self._settings.database_kind

        context = await self._schema_context.execute(
            SchemaContextRequest(
                question=request.question,
                max_tables=request.max_context_tables,
            ),
            cache_scope=request.cache_scope,
        )

        generation_request = SQLGenerationRequest.from_schema_context(
            question=request.question,
            context=context,
            database_kind=database_kind,
            max_rows=request.max_rows,
            model=request.model,
            temperature=request.temperature,
        )

        sql_result = await self._sql_generator.generate(generation_request)

        return GenerateSQLResult(
            question=request.question,
            schema_context=context,
            sql=sql_result,
        )
