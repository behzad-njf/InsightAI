"""LangChain agent ask pipeline (Phase 10.5)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from insightai.domain.exceptions import SQLGenerationError
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerRequest,
    GenerateAnswerResult,
)
from insightai.domain.models.ask import (
    AskRequest,
    AskResult,
    AskStreamEvent,
    AskStreamPhase,
    AskTimings,
)
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.observability.ask_audit import (
    build_ask_audit_complete,
    build_ask_audit_failure,
)
from insightai.infrastructure.observability.structlog_audit import NullAuditLogger
from insightai.infrastructure.rag.citations import enrich_generate_answer_result

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
    from insightai.domain.models.langchain_agent import LangChainAgentRunResult
    from insightai.domain.ports.audit_logger import IAuditLogger
    from insightai.domain.ports.langchain_agent import ILangChainAgentRunner

logger = get_logger(__name__)


class LangChainAgentAskUseCase:
    """
    Optional ask path: LangChain tool-calling agent over RAG search + read-only SQL.

    Implements ``IAskPipeline``. Streaming runs the agent synchronously then emits ``done``.
    """

    def __init__(
        self,
        agent_runner: ILangChainAgentRunner,
        generate_answer: GenerateAnswerUseCase,
        *,
        settings: Settings | None = None,
        audit: IAuditLogger | None = None,
    ) -> None:
        self._agent = agent_runner
        self._generate_answer = generate_answer
        self._settings = settings or get_settings()
        self._audit = audit or NullAuditLogger()

    async def execute(self, request: AskRequest) -> AskResult:
        try:
            return await self._execute_agent(request, stream=False)
        except SQLGenerationError as exc:
            self._log_failure(request, str(exc), error_code="sql_generation_error", stream=False)
            raise
        except Exception as exc:
            self._log_failure(request, str(exc), error_code="pipeline_error", stream=False)
            raise

    async def execute_stream(self, request: AskRequest) -> AsyncIterator[AskStreamEvent]:
        try:
            yield AskStreamEvent.status(AskStreamPhase.ROUTING)
            result = await self._execute_agent(request, stream=True)
            yield AskStreamEvent.done(result)
        except SQLGenerationError as exc:
            self._log_failure(request, str(exc), error_code="sql_generation_error", stream=True)
            yield AskStreamEvent.failure(str(exc), error_code="sql_generation_error")
        except Exception as exc:
            logger.exception("langchain_agent_stream_failed", error=str(exc))
            self._log_failure(request, str(exc), error_code="pipeline_error", stream=True)
            yield AskStreamEvent.failure(str(exc), error_code="pipeline_error")

    async def _execute_agent(self, request: AskRequest, *, stream: bool) -> AskResult:
        total_started = time.perf_counter()
        agent_result = await self._agent.run(request.question)
        result = await self._build_ask_result(request, agent_result, total_started=total_started)
        self._audit.log_ask_complete(
            build_ask_audit_complete(result, self._settings, stream=stream),
        )
        return result

    async def _build_ask_result(
        self,
        request: AskRequest,
        agent_result: LangChainAgentRunResult,
        *,
        total_started: float,
    ) -> AskResult:
        answer = await self._resolve_answer(request, agent_result)
        total_ms = (time.perf_counter() - total_started) * 1000
        timings = AskTimings(
            route_classification_ms=0.0,
            rag_retrieval_ms=(
                agent_result.rag_retrieval.retrieval_ms
                if agent_result.rag_retrieval is not None
                else 0.0
            ),
            sql_generation_ms=0.0,
            query_execution_ms=0.0,
            answer_generation_ms=max(0.0, total_ms - agent_result.agent_ms),
            total_ms=round(total_ms, 2),
        )
        return AskResult(
            question=request.question,
            route=QueryRouteKind.AGENT,
            sql=agent_result.sql,
            execution=agent_result.execution,
            answer=answer,
            rag_retrieval=agent_result.rag_retrieval,
            timings=timings,
        )

    async def _resolve_answer(
        self,
        request: AskRequest,
        agent_result: LangChainAgentRunResult,
    ) -> GenerateAnswerResult:
        if agent_result.execution is not None:
            grounded = await self._generate_answer.execute(
                GenerateAnswerRequest(
                    question=request.question,
                    run_query_result=agent_result.execution,
                    max_display_rows=request.max_display_rows,
                    model=request.answer_model,
                    temperature=request.answer_temperature,
                    document_context=(
                        _format_rag_context(agent_result.rag_retrieval)
                        if agent_result.rag_retrieval is not None
                        else None
                    ),
                ),
            )
            if agent_result.rag_retrieval is not None:
                return enrich_generate_answer_result(
                    grounded,
                    agent_result.rag_retrieval.sources,
                )
            return grounded

        empty = QueryResult(
            columns=[QueryColumn(name="_agent")],
            rows=[],
            row_count=0,
            executed_at=datetime.now(UTC),
            truncated=False,
        )
        result = GenerateAnswerResult(
            question=request.question,
            sql="",
            query_result=empty,
            answer=AnswerGenerationResult(
                answer=agent_result.answer,
                row_count=0,
                truncation_noted=False,
            ),
        )
        if agent_result.rag_retrieval is not None:
            return enrich_generate_answer_result(
                result,
                agent_result.rag_retrieval.sources,
            )
        return result


    def _log_failure(
        self,
        request: AskRequest,
        message: str,
        *,
        error_code: str | None,
        stream: bool,
    ) -> None:
        self._audit.log_ask_failure(
            build_ask_audit_failure(
                question=request.question,
                error_message=message,
                error_code=error_code,
                stream=stream,
            ),
        )


def _format_rag_context(retrieval: object | None) -> str | None:
    if retrieval is None:
        return None
    from insightai.domain.models.hybrid import RAGRetrievalResult
    from insightai.infrastructure.rag.source_format import format_rag_sources_for_prompt

    if not isinstance(retrieval, RAGRetrievalResult) or not retrieval.has_sources:
        return None
    return format_rag_sources_for_prompt(retrieval)
