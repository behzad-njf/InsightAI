"""Full NL → SQL → execute → answer pipeline (Phase 6.4)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from insightai.application.pipeline.governed_sql import prepare_governed_sql
from insightai.domain.exceptions import GovernanceDeniedError, SQLGenerationError
from insightai.domain.models.answer import GenerateAnswerRequest
from insightai.domain.models.ask import (
    AskMode,
    AskRequest,
    AskResult,
    AskStreamEvent,
    AskStreamPhase,
    AskTimings,
)
from insightai.domain.models.database import QueryResult
from insightai.domain.models.explainability import ExplainabilityBuildRequest
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.domain.models.query_execution import (
    RunQueryRequest,
    RunQueryResult,
    RunQuerySQLSource,
)
from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.models.sql_generation import GenerateSQLRequest, GenerateSQLResult
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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.application.pipeline.governed_sql import GovernedSQLPreparation
    from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
    from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
    from insightai.application.use_cases.run_query import RunQueryUseCase
    from insightai.domain.ports.audit_logger import IAuditLogger
    from insightai.domain.ports.explainability_builder import IExplainabilityBuilder
    from insightai.domain.ports.governance import IGovernanceEnforcer
    from insightai.domain.ports.sql_safety import ISQLSafetyValidator

logger = get_logger(__name__)


class AskUseCase:
    """
    Orchestrate Phases 2–6: schema context → SQL → validate → govern → validate → execute → answer.

    Implements ``IAskPipeline`` for product APIs (``POST /api/v1/chat``) and debug
    ``POST /api/v1/ask``.

    - Phase 3: ``GenerateSQLUseCase`` (LLM path includes Phase 4 post-process on generated SQL)
    - Phase 12.4: ``prepare_governed_sql`` — validate → governance → validate (before execute)
    - Phase 5: ``RunQueryUseCase`` (re-validates and executes read-only SQL)
    - Phase 6: ``GenerateAnswerUseCase`` (grounded natural-language summary)
    """

    def __init__(
        self,
        generate_sql: GenerateSQLUseCase,
        run_query: RunQueryUseCase,
        generate_answer: GenerateAnswerUseCase,
        settings: Settings | None = None,
        audit: IAuditLogger | None = None,
        governance: IGovernanceEnforcer | None = None,
        sql_validator: ISQLSafetyValidator | None = None,
        explainability: IExplainabilityBuilder | None = None,
    ) -> None:
        from insightai.infrastructure.governance.noop_enforcer import NoOpGovernanceEnforcer

        self._generate_sql = generate_sql
        self._run_query = run_query
        self._generate_answer = generate_answer
        self._settings = settings or get_settings()
        self._audit = audit or NullAuditLogger()
        self._governance = governance or NoOpGovernanceEnforcer()
        self._sql_validator = sql_validator
        self._explainability = explainability or ExplainabilityBuilder()

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
        except GovernanceDeniedError as exc:
            self._log_failure(
                request,
                str(exc),
                error_code="GOVERNANCE_DENIED",
                stream=False,
                governance_denied=True,
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
        """Run schema → SQL → govern hook → execute → answer without hybrid routing."""
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

        dry_run = request.mode == AskMode.DRY_RUN
        exec_started = time.perf_counter()
        preparation = self._prepare_governed_sql(request, sql_result)
        if dry_run:
            execution = self._build_dry_run_execution(
                request,
                preparation.sql_result,
                preparation.validated_sql,
            )
        else:
            with start_span("insightai.ask.query_execution"):
                execution = await self._run_query.execute(
                    self._build_run_query_request(request, preparation),
                )
        query_execution_ms = (time.perf_counter() - exec_started) * 1000
        record_ask_pipeline_stage(
            stage="query_execution" if not dry_run else "sql_validation",
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
            sql=preparation.sql_result,
            execution=execution,
            answer=answer,
            timings=timings,
            dry_run=dry_run,
            governance_context=request.governance_context,
            governance_decision=preparation.governance_decision,
            explainability=self._explainability.build(
                ExplainabilityBuildRequest(
                    question=request.question,
                    schema_context=preparation.sql_result.schema_context,
                    sql_generation=preparation.sql_result.sql,
                    validation=self._validation_for_explainability(preparation.validated_sql),
                    governance=preparation.governance_decision,
                    referenced_tables=list(preparation.sql_result.sql.tables_used),
                    dry_run=dry_run,
                    sql_executed=not dry_run,
                ),
            ),
        )

        logger.info(
            "ask_pipeline_complete",
            row_count=execution.query_result.row_count,
            truncated=execution.query_result.truncated,
            dry_run=dry_run,
            governance_applied=preparation.governance_decision.applied,
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

            dry_run = request.mode == AskMode.DRY_RUN
            exec_started = time.perf_counter()

            yield AskStreamEvent.status(AskStreamPhase.APPLYING_GOVERNANCE)
            with start_span(
                "insightai.ask.governance",
                attributes={"insightai.stream": True},
            ):
                preparation = self._prepare_governed_sql(request, sql_result)

            yield AskStreamEvent.status(AskStreamPhase.VALIDATING_SQL)
            if dry_run:
                execution = self._build_dry_run_execution(
                    request,
                    preparation.sql_result,
                    preparation.validated_sql,
                )
            else:
                yield AskStreamEvent.status(AskStreamPhase.EXECUTING_QUERY)
                with start_span(
                    "insightai.ask.query_execution",
                    attributes={"insightai.stream": True},
                ):
                    execution = await self._run_query.execute(
                        self._build_run_query_request(request, preparation),
                    )
            query_execution_ms = (time.perf_counter() - exec_started) * 1000
            record_ask_pipeline_stage(
                stage="query_execution" if not dry_run else "sql_validation",
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
                            sql=preparation.sql_result,
                            execution=execution,
                            answer=chunk.result,
                            timings=timings,
                            dry_run=dry_run,
                            governance_context=request.governance_context,
                            governance_decision=preparation.governance_decision,
                            explainability=self._explainability.build(
                                ExplainabilityBuildRequest(
                                    question=request.question,
                                    schema_context=preparation.sql_result.schema_context,
                                    sql_generation=preparation.sql_result.sql,
                                    validation=self._validation_for_explainability(
                                        preparation.validated_sql,
                                    ),
                                    governance=preparation.governance_decision,
                                    referenced_tables=list(preparation.sql_result.sql.tables_used),
                                    dry_run=dry_run,
                                    sql_executed=not dry_run,
                                ),
                            ),
                        )
                        logger.info(
                            "ask_pipeline_stream_complete",
                            row_count=execution.query_result.row_count,
                            truncated=execution.query_result.truncated,
                            dry_run=dry_run,
                            governance_applied=preparation.governance_decision.applied,
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
        except GovernanceDeniedError as exc:
            self._log_failure(
                request,
                str(exc),
                error_code="GOVERNANCE_DENIED",
                stream=True,
                governance_denied=True,
            )
            yield AskStreamEvent.failure(str(exc), error_code="GOVERNANCE_DENIED")
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
        governance_denied: bool = False,
    ) -> None:
        self._audit.log_ask_failure(
            build_ask_audit_failure(
                question=request.question,
                error_message=message,
                error_code=error_code,
                stream=stream,
                phase=phase,
                governance_denied=governance_denied,
            ),
        )

    def _cache_scope(self, request: AskRequest) -> str | None:
        ctx = request.governance_context
        if ctx is not None and ctx.api_key_id:
            return f"api_key:{ctx.api_key_id}"
        from insightai.infrastructure.observability.context import get_audit_context

        audit = get_audit_context()
        return audit.auth_subject if audit is not None else None

    def _enforce_readonly(self, request: AskRequest) -> bool:
        if request.enforce_readonly is not None:
            return request.enforce_readonly
        return self._settings.sql_enforce_readonly

    def _validation_for_explainability(self, sql: str) -> SQLValidationResult | None:
        if self._sql_validator is None:
            return None
        try:
            return self._sql_validator.validate(sql)
        except Exception:
            # Explainability payload is best-effort and must not block responses.
            return SQLValidationResult(
                is_valid=False,
                statement_kind=SQLStatementKind.UNKNOWN,
                violations=["Validation metadata unavailable."],
            )

    def _prepare_governed_sql(
        self,
        request: AskRequest,
        sql_result: GenerateSQLResult,
    ) -> GovernedSQLPreparation:
        with start_span("insightai.ask.governance"):
            preparation = prepare_governed_sql(
                sql_result,
                governance=self._governance,
                governance_context=request.governance_context,
                sql_validator=self._sql_validator,
                enforce_readonly=self._enforce_readonly(request),
            )
        if preparation.governance_decision.applied:
            logger.info(
                "governance_modified",
                dimensions_applied=list(preparation.governance_decision.dimensions_applied),
                column_masks_applied=list(
                    preparation.governance_decision.column_masks_applied,
                ),
            )
        return preparation

    def _build_run_query_request(
        self,
        request: AskRequest,
        preparation: GovernedSQLPreparation,
    ) -> RunQueryRequest:
        return RunQueryRequest.from_sql(
            preparation.validated_sql,
            max_rows=request.max_rows,
            timeout_seconds=request.timeout_seconds,
            enforce_readonly=request.enforce_readonly,
            cache_scope=self._cache_scope(request),
        )

    def _build_sql_request(self, request: AskRequest) -> GenerateSQLRequest:
        cache_scope = self._cache_scope(request)
        return GenerateSQLRequest(
            question=request.question,
            max_context_tables=request.max_context_tables,
            max_rows=request.max_rows,
            database_kind=request.database_kind,
            model=request.sql_model,
            temperature=request.sql_temperature,
            cache_scope=cache_scope,
            use_llm=request.use_llm,
        )

    def _build_dry_run_execution(
        self,
        request: AskRequest,
        sql_result: GenerateSQLResult,
        validated_sql: str,
    ) -> RunQueryResult:
        run_request = RunQueryRequest.from_sql(
            validated_sql,
            max_rows=request.max_rows,
            timeout_seconds=request.timeout_seconds,
            enforce_readonly=request.enforce_readonly,
            cache_scope=self._cache_scope(request),
        )
        options = run_request.to_execution_options(
            self._settings.get_query_execution_options(),
        )
        return RunQueryResult(
            sql=validated_sql,
            source=RunQuerySQLSource.GENERATED,
            query_result=QueryResult(columns=[], rows=[], row_count=0, truncated=False),
            question=request.question,
            generation=sql_result.sql,
            execution_options=options,
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
