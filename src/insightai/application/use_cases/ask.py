"""Full NL → SQL → execute → answer pipeline (Phase 6.4)."""

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
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.domain.models.query_execution import RunQueryRequest, RunQueryResult
from insightai.domain.models.sql_generation import GenerateSQLRequest, GenerateSQLResult
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.observability.ask_audit import (
    build_ask_audit_complete,
    build_ask_audit_failure,
)
from insightai.infrastructure.observability.metrics import record_ask_pipeline_stage
from insightai.infrastructure.observability.structlog_audit import NullAuditLogger
from insightai.infrastructure.observability.tracing import start_span

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
    from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
    from insightai.application.use_cases.run_query import RunQueryUseCase
    from insightai.domain.ports.audit_logger import IAuditLogger

logger = get_logger(__name__)


class AskUseCase:
    """
    Orchestrate Phases 2–6: schema context → SQL → validate → execute → answer.

    Implements ``IAskPipeline`` for product APIs (``POST /api/v1/chat``) and debug
    ``POST /api/v1/ask``.

    - Phase 3: ``GenerateSQLUseCase`` (includes Phase 4 post-process + validate on SQL)
    - Phase 5: ``RunQueryUseCase`` (composite validator + executor limits)
    - Phase 6: ``GenerateAnswerUseCase`` (grounded natural-language summary)
    """

    def __init__(
        self,
        generate_sql: GenerateSQLUseCase,
        run_query: RunQueryUseCase,
        generate_answer: GenerateAnswerUseCase,
        settings: Settings | None = None,
        audit: IAuditLogger | None = None,
    ) -> None:
        self._generate_sql = generate_sql
        self._run_query = run_query
        self._generate_answer = generate_answer
        self._settings = settings or get_settings()
        self._audit = audit or NullAuditLogger()

    async def execute(self, request: AskRequest) -> AskResult:
        try:
            return await self.execute_sql_pipeline(request, stream=False)
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

    async def execute_sql_pipeline(self, request: AskRequest, *, stream: bool) -> AskResult:
        """Run schema → SQL → execute → answer without hybrid routing (Phase 6.4)."""
        total_started = time.perf_counter()
        logger.info(
            "ask_pipeline_start",
            question_length=len(request.question.strip()),
            stream=stream,
        )

        sql_started = time.perf_counter()
        with start_span(
            "insightai.ask.sql_generation",
            attributes={"insightai.stream": stream},
        ):
            sql_result = await self._generate_sql.execute(
                self._build_sql_request(request),
            )
        sql_generation_ms = (time.perf_counter() - sql_started) * 1000
        record_ask_pipeline_stage(
            stage="sql_generation",
            duration_seconds=sql_generation_ms / 1000,
        )

        if not sql_result.sql.has_sql:
            explanation = sql_result.sql.explanation.strip() or "No SQL was produced."
            raise SQLGenerationError(
                f"Cannot execute query: {explanation}",
            )

        exec_started = time.perf_counter()
        with start_span("insightai.ask.query_execution"):
            execution = await self._run_query.execute(
                self._build_run_query_request(request, sql_result),
            )
        query_execution_ms = (time.perf_counter() - exec_started) * 1000
        record_ask_pipeline_stage(
            stage="query_execution",
            duration_seconds=query_execution_ms / 1000,
        )

        answer_started = time.perf_counter()
        with start_span("insightai.ask.answer_generation"):
            answer = await self._generate_answer.execute(
                self._build_answer_request(request, execution),
            )
        answer_generation_ms = (time.perf_counter() - answer_started) * 1000
        record_ask_pipeline_stage(
            stage="answer_generation",
            duration_seconds=answer_generation_ms / 1000,
        )

        total_ms = (time.perf_counter() - total_started) * 1000
        timings = AskTimings(
            sql_generation_ms=round(sql_generation_ms, 2),
            query_execution_ms=round(query_execution_ms, 2),
            answer_generation_ms=round(answer_generation_ms, 2),
            total_ms=round(total_ms, 2),
        )

        result = AskResult(
            question=request.question,
            route=QueryRouteKind.SQL,
            sql=sql_result,
            execution=execution,
            answer=answer,
            timings=timings,
        )

        logger.info(
            "ask_pipeline_complete",
            row_count=execution.query_result.row_count,
            truncated=execution.query_result.truncated,
            sql_generation_ms=timings.sql_generation_ms,
            query_execution_ms=timings.query_execution_ms,
            answer_generation_ms=timings.answer_generation_ms,
            total_ms=timings.total_ms,
            stream=stream,
        )
        self._audit.log_ask_complete(
            build_ask_audit_complete(result, self._settings, stream=stream),
        )
        return result

    async def execute_stream(self, request: AskRequest) -> AsyncIterator[AskStreamEvent]:
        """
        Stream pipeline progress and answer tokens, then ``done`` with full ``AskResult``.

        On failure yields ``error`` and ends the stream (no exception propagated to callers
        that prefer event-based handling).
        """
        total_started = time.perf_counter()
        sql_generation_ms = 0.0
        query_execution_ms = 0.0
        answer_generation_ms = 0.0

        logger.info(
            "ask_pipeline_stream_start",
            question_length=len(request.question.strip()),
        )

        try:
            yield AskStreamEvent.status(AskStreamPhase.GENERATING_SQL)
            sql_started = time.perf_counter()
            with start_span("insightai.ask.sql_generation", attributes={"insightai.stream": True}):
                sql_result = await self._generate_sql.execute(self._build_sql_request(request))
            sql_generation_ms = (time.perf_counter() - sql_started) * 1000
            record_ask_pipeline_stage(
                stage="sql_generation",
                duration_seconds=sql_generation_ms / 1000,
            )

            if not sql_result.sql.has_sql:
                explanation = sql_result.sql.explanation.strip() or "No SQL was produced."
                message = f"Cannot execute query: {explanation}"
                self._log_failure(
                    request,
                    message,
                    error_code="sql_generation_error",
                    stream=True,
                    phase=AskStreamPhase.GENERATING_SQL.value,
                )
                yield AskStreamEvent.failure(message, error_code="sql_generation_error")
                return

            yield AskStreamEvent.status(AskStreamPhase.EXECUTING_QUERY)
            exec_started = time.perf_counter()
            with start_span("insightai.ask.query_execution", attributes={"insightai.stream": True}):
                execution = await self._run_query.execute(
                    self._build_run_query_request(request, sql_result),
                )
            query_execution_ms = (time.perf_counter() - exec_started) * 1000
            record_ask_pipeline_stage(
                stage="query_execution",
                duration_seconds=query_execution_ms / 1000,
            )

            yield AskStreamEvent.status(AskStreamPhase.GENERATING_ANSWER)
            answer_started = time.perf_counter()
            answer_request = self._build_answer_request(request, execution)

            with start_span(
                "insightai.ask.answer_generation",
                attributes={"insightai.stream": True},
            ):
                async for chunk in self._generate_answer.execute_stream(answer_request):
                    if chunk.kind == "token" and chunk.text_delta:
                        yield AskStreamEvent.token(chunk.text_delta)
                    elif chunk.kind == "done" and chunk.result is not None:
                        answer_generation_ms = (time.perf_counter() - answer_started) * 1000
                        record_ask_pipeline_stage(
                            stage="answer_generation",
                            duration_seconds=answer_generation_ms / 1000,
                        )
                        total_ms = (time.perf_counter() - total_started) * 1000
                        timings = AskTimings(
                            sql_generation_ms=round(sql_generation_ms, 2),
                            query_execution_ms=round(query_execution_ms, 2),
                            answer_generation_ms=round(answer_generation_ms, 2),
                            total_ms=round(total_ms, 2),
                        )
                        ask_result = AskResult(
                            question=request.question,
                            sql=sql_result,
                            execution=execution,
                            answer=chunk.result,
                            timings=timings,
                        )
                        logger.info(
                            "ask_pipeline_stream_complete",
                            row_count=execution.query_result.row_count,
                            truncated=execution.query_result.truncated,
                            total_ms=timings.total_ms,
                        )
                        self._audit.log_ask_complete(
                            build_ask_audit_complete(ask_result, self._settings, stream=True),
                        )
                        yield AskStreamEvent.done(ask_result)
                        return

            message = "Answer stream ended without a result."
            self._log_failure(
                request,
                message,
                error_code="answer_generation_error",
                stream=True,
                phase=AskStreamPhase.GENERATING_ANSWER.value,
            )
            yield AskStreamEvent.failure(message, error_code="answer_generation_error")
        except SQLGenerationError as exc:
            self._log_failure(
                request,
                str(exc),
                error_code="sql_generation_error",
                stream=True,
            )
            yield AskStreamEvent.failure(str(exc), error_code="sql_generation_error")
        except Exception as exc:
            logger.exception("ask_pipeline_stream_failed", error=str(exc))
            self._log_failure(
                request,
                str(exc),
                error_code="pipeline_error",
                stream=True,
            )
            yield AskStreamEvent.failure(str(exc), error_code="pipeline_error")

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

    def _audit_cache_scope(self) -> str | None:
        from insightai.infrastructure.observability.context import get_audit_context

        audit = get_audit_context()
        return audit.auth_subject if audit is not None else None

    def _build_run_query_request(
        self,
        request: AskRequest,
        sql_result: GenerateSQLResult,
    ) -> RunQueryRequest:
        return RunQueryRequest.from_generate_sql(
            sql_result,
            max_rows=request.max_rows,
            timeout_seconds=request.timeout_seconds,
            enforce_readonly=request.enforce_readonly,
            cache_scope=self._audit_cache_scope(),
        )

    def _build_sql_request(self, request: AskRequest) -> GenerateSQLRequest:
        cache_scope = self._audit_cache_scope()
        return GenerateSQLRequest(
            question=request.question,
            max_context_tables=request.max_context_tables,
            max_rows=request.max_rows,
            database_kind=request.database_kind,
            model=request.sql_model,
            temperature=request.sql_temperature,
            cache_scope=cache_scope,
        )

    def _build_answer_request(
        self,
        request: AskRequest,
        execution: RunQueryResult,
    ) -> GenerateAnswerRequest:
        return GenerateAnswerRequest(
            question=request.question,
            run_query_result=execution,
            max_display_rows=request.max_display_rows,
            model=request.answer_model,
            temperature=request.answer_temperature,
        )
