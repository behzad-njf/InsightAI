"""LangChain tools wrapping InsightAI use cases (Phase 10.5)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.models.sql_generation import GenerateSQLRequest
from insightai.infrastructure.ai.langchain.tool_context import LangChainAgentToolContext
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.prompts.result_format import format_query_result_for_prompt
from insightai.infrastructure.rag.source_format import format_rag_sources_for_prompt

logger = get_logger(__name__)

SEARCH_DOCUMENTS_DESCRIPTION = (
    "Search ingested policy and help documents by semantic similarity. "
    "Use for definitions, procedures, campus policies, and handbook text "
    "— not for counts or trends."
)

RUN_SQL_ANALYTICS_DESCRIPTION = (
    "Generate and execute a read-only SQL query against the analytics database. "
    "Use for counts, totals, trends, comparisons, and tabular metrics. "
    "Never use for pure policy wording unless numbers are required."
)


def build_langchain_tools(
    *,
    retrieve_rag: RetrieveRAGContextUseCase,
    generate_sql: GenerateSQLUseCase,
    run_query: RunQueryUseCase,
    settings: Settings,
    context: LangChainAgentToolContext,
) -> list[Callable[..., Coroutine[Any, Any, str]]]:
    """Build async tool callables for ``langchain.agents.create_agent`` (LangChain 1.x)."""

    async def search_documents(query: str) -> str:
        context.record_tool("search_documents")
        retrieval = await retrieve_rag.execute(query)
        context.rag_retrieval = retrieval
        logger.info("langchain_tool_search_documents", hits=len(retrieval.sources))
        return format_rag_sources_for_prompt(retrieval)

    async def run_sql_analytics(question: str) -> str:
        context.record_tool("run_sql_analytics")
        sql_result = await generate_sql.execute(
            GenerateSQLRequest(
                question=question,
                max_rows=settings.sql_max_rows,
            ),
        )
        context.sql = sql_result

        if not sql_result.sql.has_sql:
            explanation = sql_result.sql.explanation.strip() or "No SQL was produced."
            return f"SQL generation failed: {explanation}"

        from insightai.domain.models.query_execution import RunQueryRequest

        execution = await run_query.execute(
            RunQueryRequest.from_generate_sql(sql_result),
        )
        context.execution = execution
        table = format_query_result_for_prompt(
            execution.query_result,
            max_rows=min(20, settings.answer_max_prompt_rows),
        )
        logger.info(
            "langchain_tool_run_sql_analytics",
            row_count=execution.query_result.row_count,
        )
        return (
            f"Executed read-only SQL:\n{execution.sql}\n\n"
            f"Rows returned: {execution.query_result.row_count}\n"
            f"Truncated: {execution.query_result.truncated}\n\n{table}"
        )

    search_documents.__doc__ = SEARCH_DOCUMENTS_DESCRIPTION
    run_sql_analytics.__doc__ = RUN_SQL_ANALYTICS_DESCRIPTION
    return [search_documents, run_sql_analytics]
