"""Generate read-only SQL from a natural language question (Phase 3.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.schema import SchemaContextRequest
from insightai.domain.models.semantic import TrustedSQLMatchRequest
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    GenerateSQLResult,
    SQLGenerationRequest,
    SQLGenerationResult,
)

# Always prepended to SQL domain context when Knowledge injection is enabled.
_PINNED_SQL_KNOWLEDGE_FILES: tuple[str, ...] = (
    "sql_never_guess_schema.md"
)

if TYPE_CHECKING:
    from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
    from insightai.application.use_cases.match_trusted_sql import MatchTrustedSQLUseCase
    from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
    from insightai.domain.ports.sql_generator import ISQLGenerator
    from insightai.infrastructure.config.settings import Settings


class GenerateSQLUseCase:
    """
    Orchestrate Phase 2 schema context + Phase 3 SQL generation.

    Flow: question → schema context → optional trusted match (Phase 11) → LLM SQL.
    """

    def __init__(
        self,
        schema_context_use_case: BuildSchemaContextUseCase,
        sql_generator: ISQLGenerator,
        settings: Settings | None = None,
        *,
        retrieve_rag: RetrieveRAGContextUseCase | None = None,
        match_trusted: MatchTrustedSQLUseCase | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._schema_context = schema_context_use_case
        self._sql_generator = sql_generator
        self._settings = settings or get_settings()
        self._retrieve_rag = retrieve_rag
        self._match_trusted = match_trusted

    async def execute(self, request: GenerateSQLRequest) -> GenerateSQLResult:
        database_kind = request.database_kind or self._settings.database_kind

        context = await self._schema_context.execute(
            SchemaContextRequest(
                question=request.question,
                max_tables=request.max_context_tables,
            ),
            cache_scope=request.cache_scope,
        )

        domain_context = await self._load_domain_context(request.question)

        trusted_request = TrustedSQLMatchRequest(
            question=request.question,
            database_kind=database_kind,
        )

        if self._match_trusted is not None:
            question_match = self._match_trusted.execute(trusted_request)
            if question_match.matched and not request.use_llm:
                sql_result = SQLGenerationResult.from_trusted_match(
                    question_match,
                    schema_table_names=context.table_names,
                )
                return GenerateSQLResult(
                    question=request.question,
                    schema_context=context,
                    sql=sql_result,
                )

        generation_request = SQLGenerationRequest.from_schema_context(
            question=request.question,
            context=context,
            database_kind=database_kind,
            max_rows=request.max_rows,
            model=request.model,
            temperature=request.temperature,
            domain_context=domain_context,
        )

        sql_result = await self._sql_generator.generate(generation_request)

        if self._match_trusted is not None and sql_result.has_sql:
            sql_match = self._match_trusted.execute(
                TrustedSQLMatchRequest(
                    question=request.question,
                    sql=sql_result.sql,
                    database_kind=database_kind,
                ),
            )
            sql_result = sql_result.with_trusted_sql_verification(sql_match)

        return GenerateSQLResult(
            question=request.question,
            schema_context=context,
            sql=sql_result,
        )

    async def _load_domain_context(self, question: str) -> str | None:
        """Inject pinned + retrieved Knowledge/ excerpts for SQL generation."""
        if not self._settings.sql_knowledge_context_enabled:
            return None

        sections: list[str] = []
        pinned = self._load_pinned_sql_knowledge()
        if pinned:
            sections.append(pinned)

        if self._retrieve_rag is not None:
            from insightai.infrastructure.rag.source_format import format_rag_sources_for_prompt

            retrieval = await self._retrieve_rag.execute(
                question,
                top_k=self._settings.sql_knowledge_top_k,
            )
            if retrieval.sources:
                sections.append(format_rag_sources_for_prompt(retrieval))

        if not sections:
            return None
        return "\n\n---\n\n".join(sections)

    def _load_pinned_sql_knowledge(self) -> str | None:
        """Load mandatory Knowledge files so SQL rules are not missed by retrieval."""
        knowledge_dir = self._settings.resolved_rag_knowledge_path()
        parts: list[str] = []
        for filename in _PINNED_SQL_KNOWLEDGE_FILES:
            path = knowledge_dir / filename
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        if not parts:
            return None
        return "\n\n---\n\n".join(parts)
