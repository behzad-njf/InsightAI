"""Map ask pipeline results to audit records."""

from __future__ import annotations

from insightai.domain.models.ask import AskResult
from insightai.domain.models.audit import (
    AskAuditComplete,
    AskAuditFailure,
    TokenUsageSummary,
)
from insightai.domain.models.llm import TokenUsage
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.context import get_audit_context


def _sum_tokens(*usages: TokenUsage) -> int | None:
    totals = [usage.total_tokens for usage in usages if usage.total_tokens is not None]
    if not totals:
        return None
    return sum(totals)


def token_usage_from_ask_result(result: AskResult) -> TokenUsageSummary:
    sql_usage = result.sql.sql.usage
    answer_usage = result.answer.answer.usage
    return TokenUsageSummary(
        sql_prompt_tokens=sql_usage.prompt_tokens,
        sql_completion_tokens=sql_usage.completion_tokens,
        sql_total_tokens=sql_usage.total_tokens,
        answer_prompt_tokens=answer_usage.prompt_tokens,
        answer_completion_tokens=answer_usage.completion_tokens,
        answer_total_tokens=answer_usage.total_tokens,
        combined_total_tokens=_sum_tokens(sql_usage, answer_usage),
    )


def build_ask_audit_complete(
    result: AskResult,
    settings: Settings,
    *,
    stream: bool = False,
) -> AskAuditComplete:
    ctx = get_audit_context()
    request_id = request_id_var.get() or "unknown"
    question = result.question.strip()

    sql_text: str | None = None
    if settings.observability_log_sql and result.sql.sql.has_sql:
        sql_text = result.execution.sql.strip() or result.sql.sql.sql.strip()

    question_text: str | None = None
    if settings.observability_log_question:
        question_text = question

    return AskAuditComplete(
        request_id=request_id,
        question_length=len(question),
        session_id=ctx.session_id if ctx else None,
        auth_subject=ctx.auth_subject if ctx else None,
        stream=stream,
        schema_table_count=len(result.sql.schema_context.table_names),
        tables_used=list(result.sql.sql.tables_used),
        row_count=result.execution.query_result.row_count,
        truncated=result.execution.query_result.truncated,
        timings=result.timings,
        token_usage=token_usage_from_ask_result(result),
        sql_model=result.sql.sql.model,
        answer_model=result.answer.answer.model,
        sql_provider=result.sql.sql.provider.value if result.sql.sql.provider else None,
        answer_provider=(
            result.answer.answer.provider.value if result.answer.answer.provider else None
        ),
        question_text=question_text,
        sql_text=sql_text,
    )


def build_ask_audit_failure(
    *,
    question: str,
    error_message: str,
    stream: bool = False,
    error_code: str | None = None,
    phase: str | None = None,
) -> AskAuditFailure:
    ctx = get_audit_context()
    request_id = request_id_var.get() or "unknown"
    return AskAuditFailure(
        request_id=request_id,
        question_length=len(question.strip()),
        error_message=error_message,
        error_code=error_code,
        session_id=ctx.session_id if ctx else None,
        auth_subject=ctx.auth_subject if ctx else None,
        stream=stream,
        phase=phase,
    )
