"""Hybrid SQL + RAG ask pipeline (Phase 10.4)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from insightai.domain.exceptions import SQLGenerationError
from insightai.domain.models.answer import GenerateAnswerRequest
from insightai.domain.models.ask import (
    AskRequest,
    AskResult,
    AskStreamEvent,
    AskStreamPhase,
    AskTimings,
)
from insightai.domain.models.explainability import ExplainabilityBuildRequest
from insightai.domain.models.hybrid import QueryRouteKind, RouteClassification
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.explainability.builder import ExplainabilityBuilder
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.observability.ask_audit import (
    build_ask_audit_complete,
    build_ask_audit_failure,
)
from insightai.infrastructure.observability.metrics import record_ask_pipeline_stage
from insightai.infrastructure.observability.structlog_audit import NullAuditLogger
from insightai.infrastructure.observability.tracing import start_span
from insightai.infrastructure.rag.citations import enrich_generate_answer_result
from insightai.infrastructure.rag.source_format import format_rag_sources_for_prompt

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.application.use_cases.ask import AskUseCase
    from insightai.application.use_cases.classify_query_route import ClassifyQueryRouteUseCase
    from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
    from insightai.application.use_cases.generate_rag_answer import GenerateRAGAnswerUseCase
    from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
    from insightai.domain.ports.audit_logger import IAuditLogger
    from insightai.domain.ports.explainability_builder import IExplainabilityBuilder

logger = get_logger(__name__)


class HybridAskUseCase:
    """
    Route questions to SQL analytics, document RAG, or both.

    Delegates the SQL path to ``AskUseCase``; uses vector retrieval + RAG answer for docs.
    """

    def __init__(
        self,
        sql_ask: AskUseCase,
        classify_route: ClassifyQueryRouteUseCase,
        retrieve_rag: RetrieveRAGContextUseCase,
        generate_rag_answer: GenerateRAGAnswerUseCase,
        generate_answer: GenerateAnswerUseCase,
        *,
        settings: Settings | None = None,
        audit: IAuditLogger | None = None,
        explainability: IExplainabilityBuilder | None = None,
    ) -> None:
        self._sql_ask = sql_ask
        self._classify_route = classify_route
        self._retrieve_rag = retrieve_rag
        self._generate_rag_answer = generate_rag_answer
        self._generate_answer = generate_answer
        self._settings = settings or get_settings()
        self._audit = audit or NullAuditLogger()
        self._explainability = explainability or ExplainabilityBuilder()

    async def execute(self, request: AskRequest) -> AskResult:
        try:
            return await self._execute_routed(request, stream=False)
        except SQLGenerationError as exc:
            self._log_failure(
                request,
                str(exc),
                error_code="sql_generation_error",
                stream=False,
            )
            raise
        except Exception as exc:
            self._log_failure(
                request,
                str(exc),
                error_code="pipeline_error",
                stream=False,
            )
            raise

    async def execute_stream(self, request: AskRequest) -> AsyncIterator[AskStreamEvent]:
        total_started = time.perf_counter()
        route_classification_ms = 0.0
        rag_retrieval_ms = 0.0
        answer_generation_ms = 0.0
        stream_attrs = {"insightai.stream": True}

        try:
            yield AskStreamEvent.status(AskStreamPhase.ROUTING)
            route_started = time.perf_counter()
            with start_span("insightai.ask.route_classification", attributes=stream_attrs):
                classification = self._resolve_route(request)
                route = classification.route
            route_classification_ms = (time.perf_counter() - route_started) * 1000

            if route in (QueryRouteKind.RAG, QueryRouteKind.BOTH):
                yield AskStreamEvent.status(AskStreamPhase.RETRIEVING_DOCUMENTS)
                rag_started = time.perf_counter()
                with start_span("insightai.ask.rag_retrieval", attributes=stream_attrs):
                    retrieval = await self._retrieve_rag.execute(request.question)
                rag_retrieval_ms = (time.perf_counter() - rag_started) * 1000
                record_ask_pipeline_stage(
                    stage="rag_retrieval",
                    duration_seconds=rag_retrieval_ms / 1000,
                )
            else:
                retrieval = None

            if route == QueryRouteKind.RAG:
                yield AskStreamEvent.status(AskStreamPhase.GENERATING_ANSWER)
                answer_started = time.perf_counter()
                assert retrieval is not None
                async for chunk in self._generate_rag_answer.execute_stream(
                    question=request.question,
                    retrieval=retrieval,
                    model=request.answer_model,
                    temperature=request.answer_temperature,
                ):
                    if chunk.kind == "token" and chunk.text_delta:
                        yield AskStreamEvent.token(chunk.text_delta)
                    elif chunk.kind == "done" and chunk.result is not None:
                        answer_generation_ms = (time.perf_counter() - answer_started) * 1000
                        result = self._build_rag_result(
                            request,
                            route=route,
                            classification=classification,
                            answer=chunk.result,
                            retrieval=retrieval,
                            timings=self._timings(
                                total_started=total_started,
                                route_classification_ms=route_classification_ms,
                                rag_retrieval_ms=rag_retrieval_ms,
                                answer_generation_ms=answer_generation_ms,
                            ),
                        )
                        self._audit.log_ask_complete(
                            build_ask_audit_complete(result, self._settings, stream=True),
                        )
                        yield AskStreamEvent.done(result)
                        return
                yield AskStreamEvent.failure(
                    "RAG answer stream ended without a result.",
                    error_code="answer_generation_error",
                )
                return

            if route == QueryRouteKind.SQL:
                async for event in self._sql_ask.execute_stream(request):
                    yield _with_route_metadata(event, route=route, classification=classification)
                return

            assert route == QueryRouteKind.BOTH
            assert retrieval is not None
            async for event in self._stream_both(
                request,
                retrieval=retrieval,
                route=route,
                classification=classification,
                route_classification_ms=route_classification_ms,
                rag_retrieval_ms=rag_retrieval_ms,
                total_started=total_started,
            ):
                yield event
        except SQLGenerationError as exc:
            self._log_failure(request, str(exc), error_code="sql_generation_error", stream=True)
            yield AskStreamEvent.failure(str(exc), error_code="sql_generation_error")
        except Exception as exc:
            logger.exception("hybrid_ask_stream_failed", error=str(exc))
            self._log_failure(request, str(exc), error_code="pipeline_error", stream=True)
            yield AskStreamEvent.failure(str(exc), error_code="pipeline_error")

    async def _execute_routed(self, request: AskRequest, *, stream: bool) -> AskResult:
        total_started = time.perf_counter()
        route_started = time.perf_counter()
        with start_span(
            "insightai.ask.route_classification",
            attributes={"insightai.stream": stream},
        ):
            classification = self._resolve_route(request)
            route = classification.route
        route_classification_ms = (time.perf_counter() - route_started) * 1000

        if route == QueryRouteKind.RAG:
            return await self._execute_rag_only(
                request,
                route=route,
                classification=classification,
                total_started=total_started,
                route_classification_ms=route_classification_ms,
                stream=stream,
            )

        if route == QueryRouteKind.SQL:
            result = await self._sql_ask.execute_sql_pipeline(request, stream=stream)
            explainability = result.explainability
            if explainability is not None:
                explainability = explainability.model_copy(
                    update={
                        "route": route,
                        "route_rationale": classification.rationale,
                        "route_confidence": classification.confidence,
                    },
                )
            return result.model_copy(
                update={
                    "route": route,
                    "explainability": explainability,
                    "timings": result.timings.model_copy(
                        update={"route_classification_ms": round(route_classification_ms, 2)},
                    ),
                },
            )

        return await self._execute_both(
            request,
            route=route,
            classification=classification,
            total_started=total_started,
            route_classification_ms=route_classification_ms,
            stream=stream,
        )

    async def _execute_rag_only(
        self,
        request: AskRequest,
        *,
        route: QueryRouteKind,
        classification: RouteClassification,
        total_started: float,
        route_classification_ms: float,
        stream: bool,
    ) -> AskResult:
        rag_started = time.perf_counter()
        with start_span("insightai.ask.rag_retrieval", attributes={"insightai.stream": stream}):
            retrieval = await self._retrieve_rag.execute(request.question)
        rag_retrieval_ms = (time.perf_counter() - rag_started) * 1000
        record_ask_pipeline_stage(
            stage="rag_retrieval",
            duration_seconds=rag_retrieval_ms / 1000,
        )

        if (
            not retrieval.has_sources
            and self._settings.rag_fallback_to_sql_on_empty_index
        ):
            logger.info("hybrid_rag_empty_fallback_sql")
            return await self._sql_ask.execute_sql_pipeline(request, stream=stream)

        answer_started = time.perf_counter()
        with start_span("insightai.ask.answer_generation", attributes={"insightai.stream": stream}):
            answer = await self._generate_rag_answer.execute(
                question=request.question,
                retrieval=retrieval,
                model=request.answer_model,
                temperature=request.answer_temperature,
            )
        answer_generation_ms = (time.perf_counter() - answer_started) * 1000
        record_ask_pipeline_stage(
            stage="answer_generation",
            duration_seconds=answer_generation_ms / 1000,
        )

        result = self._build_rag_result(
            request,
            route=route,
            classification=classification,
            answer=answer,
            retrieval=retrieval,
            timings=self._timings(
                total_started=total_started,
                route_classification_ms=route_classification_ms,
                rag_retrieval_ms=rag_retrieval_ms,
                answer_generation_ms=answer_generation_ms,
            ),
        )
        self._audit.log_ask_complete(
            build_ask_audit_complete(result, self._settings, stream=stream),
        )
        return result

    async def _execute_both(
        self,
        request: AskRequest,
        *,
        route: QueryRouteKind,
        classification: RouteClassification,
        total_started: float,
        route_classification_ms: float,
        stream: bool,
    ) -> AskResult:
        rag_started = time.perf_counter()
        with start_span("insightai.ask.rag_retrieval", attributes={"insightai.stream": stream}):
            retrieval = await self._retrieve_rag.execute(request.question)
        rag_retrieval_ms = (time.perf_counter() - rag_started) * 1000
        record_ask_pipeline_stage(
            stage="rag_retrieval",
            duration_seconds=rag_retrieval_ms / 1000,
        )

        sql_result = await self._sql_ask.execute_sql_pipeline(request, stream=stream)
        document_context = format_rag_sources_for_prompt(retrieval)

        answer_started = time.perf_counter()
        with start_span("insightai.ask.answer_generation", attributes={"insightai.stream": stream}):
            answer = await self._generate_answer.execute(
                GenerateAnswerRequest(
                    question=request.question,
                    run_query_result=sql_result.execution,
                    max_display_rows=request.max_display_rows,
                    model=request.answer_model,
                    temperature=request.answer_temperature,
                    document_context=document_context,
                ),
            )
            answer = enrich_generate_answer_result(answer, retrieval.sources)
        answer_generation_ms = (time.perf_counter() - answer_started) * 1000

        timings = AskTimings(
            route_classification_ms=round(route_classification_ms, 2),
            rag_retrieval_ms=round(rag_retrieval_ms, 2),
            sql_generation_ms=sql_result.timings.sql_generation_ms,
            query_execution_ms=sql_result.timings.query_execution_ms,
            answer_generation_ms=round(answer_generation_ms, 2),
            total_ms=round((time.perf_counter() - total_started) * 1000, 2),
        )
        result = AskResult(
            question=request.question,
            route=route,
            sql=sql_result.sql,
            execution=sql_result.execution,
            answer=answer,
            rag_retrieval=retrieval,
            timings=timings,
            explainability=self._explainability.build(
                ExplainabilityBuildRequest(
                    question=request.question,
                    route=classification,
                    schema_context=(
                        sql_result.sql.schema_context if sql_result.sql is not None else None
                    ),
                    sql_generation=sql_result.sql.sql if sql_result.sql is not None else None,
                    governance=sql_result.governance_decision,
                    rag_retrieval=retrieval,
                    referenced_tables=(
                        list(sql_result.sql.sql.tables_used) if sql_result.sql is not None else []
                    ),
                    dry_run=sql_result.dry_run,
                    sql_executed=not sql_result.dry_run,
                ),
            ),
        )
        self._audit.log_ask_complete(
            build_ask_audit_complete(result, self._settings, stream=stream),
        )
        return result

    async def _stream_both(
        self,
        request: AskRequest,
        *,
        retrieval: object,
        route: QueryRouteKind,
        classification: RouteClassification,
        route_classification_ms: float,
        rag_retrieval_ms: float,
        total_started: float,
    ) -> AsyncIterator[AskStreamEvent]:
        from insightai.domain.models.hybrid import RAGRetrievalResult

        assert isinstance(retrieval, RAGRetrievalResult)
        document_context = format_rag_sources_for_prompt(retrieval)
        sql_generation_ms = 0.0
        query_execution_ms = 0.0

        async for event in self._sql_ask.execute_stream(request):
            if event.kind == "status":
                yield event
            elif event.kind == "token":
                continue
            elif event.kind == "error":
                yield event
                return
            elif event.kind == "done" and event.result is not None:
                sql_result = event.result
                sql_generation_ms = sql_result.timings.sql_generation_ms
                query_execution_ms = sql_result.timings.query_execution_ms
                yield AskStreamEvent.status(AskStreamPhase.GENERATING_ANSWER)
                answer_started = time.perf_counter()
                answer_request = GenerateAnswerRequest(
                    question=request.question,
                    run_query_result=sql_result.execution,
                    max_display_rows=request.max_display_rows,
                    model=request.answer_model,
                    temperature=request.answer_temperature,
                    document_context=document_context,
                )
                async for chunk in self._generate_answer.execute_stream(answer_request):
                    if chunk.kind == "token" and chunk.text_delta:
                        yield AskStreamEvent.token(chunk.text_delta)
                    elif chunk.kind == "done" and chunk.result is not None:
                        enriched_answer = enrich_generate_answer_result(
                            chunk.result,
                            retrieval.sources,
                        )
                        answer_generation_ms = (time.perf_counter() - answer_started) * 1000
                        timings = AskTimings(
                            route_classification_ms=round(route_classification_ms, 2),
                            rag_retrieval_ms=round(rag_retrieval_ms, 2),
                            sql_generation_ms=sql_generation_ms,
                            query_execution_ms=query_execution_ms,
                            answer_generation_ms=round(answer_generation_ms, 2),
                            total_ms=round((time.perf_counter() - total_started) * 1000, 2),
                        )
                        hybrid_result = AskResult(
                            question=request.question,
                            route=route,
                            sql=sql_result.sql,
                            execution=sql_result.execution,
                            answer=enriched_answer,
                            rag_retrieval=retrieval,
                            timings=timings,
                            explainability=self._explainability.build(
                                ExplainabilityBuildRequest(
                                    question=request.question,
                                    route=classification,
                                    schema_context=(
                                        sql_result.sql.schema_context
                                        if sql_result.sql is not None
                                        else None
                                    ),
                                    sql_generation=(
                                        sql_result.sql.sql if sql_result.sql is not None else None
                                    ),
                                    governance=sql_result.governance_decision,
                                    rag_retrieval=retrieval,
                                    referenced_tables=(
                                        list(sql_result.sql.sql.tables_used)
                                        if sql_result.sql is not None
                                        else []
                                    ),
                                    dry_run=sql_result.dry_run,
                                    sql_executed=not sql_result.dry_run,
                                ),
                            ),
                        )
                        self._audit.log_ask_complete(
                            build_ask_audit_complete(
                                hybrid_result,
                                self._settings,
                                stream=True,
                            ),
                        )
                        yield AskStreamEvent.done(hybrid_result)
                        return
                yield AskStreamEvent.failure(
                    "Hybrid answer stream ended without a result.",
                    error_code="answer_generation_error",
                )
                return

    def _resolve_route(self, request: AskRequest) -> RouteClassification:
        classification = self._classify_route.execute(
            request.question,
            requested_route=request.route,
        )
        route = classification.route
        logger.info(
            "hybrid_route_selected",
            route=route.value,
            confidence=classification.confidence,
            sql_signals=classification.sql_signals,
            rag_signals=classification.rag_signals,
        )
        return classification

    def _build_rag_result(
        self,
        request: AskRequest,
        *,
        route: QueryRouteKind,
        classification: RouteClassification,
        answer: object,
        retrieval: object,
        timings: AskTimings,
    ) -> AskResult:
        from insightai.domain.models.answer import GenerateAnswerResult
        from insightai.domain.models.hybrid import RAGRetrievalResult

        assert isinstance(answer, GenerateAnswerResult)
        assert isinstance(retrieval, RAGRetrievalResult)
        return AskResult(
            question=request.question,
            route=route,
            answer=answer,
            rag_retrieval=retrieval,
            timings=timings,
            explainability=self._explainability.build(
                ExplainabilityBuildRequest(
                    question=request.question,
                    route=classification,
                    rag_retrieval=retrieval,
                    dry_run=False,
                    sql_executed=False,
                ),
            ),
        )

    def _timings(
        self,
        *,
        total_started: float,
        route_classification_ms: float,
        rag_retrieval_ms: float,
        answer_generation_ms: float,
        sql_generation_ms: float = 0.0,
        query_execution_ms: float = 0.0,
    ) -> AskTimings:
        return AskTimings(
            route_classification_ms=round(route_classification_ms, 2),
            rag_retrieval_ms=round(rag_retrieval_ms, 2),
            sql_generation_ms=round(sql_generation_ms, 2),
            query_execution_ms=round(query_execution_ms, 2),
            answer_generation_ms=round(answer_generation_ms, 2),
            total_ms=round((time.perf_counter() - total_started) * 1000, 2),
        )

    def _log_failure(
        self,
        request: AskRequest,
        message: str,
        *,
        error_code: str | None,
        stream: bool,
        phase: str | None = None,
    ) -> None:
        self._audit.log_ask_failure(
            build_ask_audit_failure(
                question=request.question,
                error_message=message,
                error_code=error_code,
                stream=stream,
                phase=phase,
            ),
        )


def _with_route_metadata(
    event: AskStreamEvent,
    *,
    route: QueryRouteKind,
    classification: RouteClassification,
) -> AskStreamEvent:
    if event.kind != "done" or event.result is None:
        return event
    explainability = event.result.explainability
    if explainability is not None:
        explainability = explainability.model_copy(
            update={
                "route": route,
                "route_rationale": classification.rationale,
                "route_confidence": classification.confidence,
            },
        )
    return AskStreamEvent.done(
        event.result.model_copy(update={"route": route, "explainability": explainability}),
    )
