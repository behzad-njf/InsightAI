"""Unit tests for StructlogAuditLogger (Phase 8.1)."""

from __future__ import annotations

from unittest.mock import MagicMock

from insightai.domain.models.ask import AskTimings
from insightai.domain.models.audit import (
    AskAuditComplete,
    AskAuditFailure,
    LLMUsageAuditRecord,
    TokenUsageSummary,
)
from insightai.infrastructure.observability.structlog_audit import (
    NullAuditLogger,
    StructlogAuditLogger,
)
from tests.conftest import make_settings


def _complete_record(
    *,
    sql_text: str | None = None,
    question_text: str | None = None,
) -> AskAuditComplete:
    return AskAuditComplete(
        request_id="req-1",
        question_length=12,
        schema_table_count=1,
        row_count=0,
        timings=AskTimings(
            sql_generation_ms=1.0,
            query_execution_ms=2.0,
            answer_generation_ms=3.0,
            total_ms=6.0,
        ),
        token_usage=TokenUsageSummary(combined_total_tokens=42),
        sql_text=sql_text,
        question_text=question_text,
    )


def test_null_audit_logger_is_noop() -> None:
    logger = NullAuditLogger()
    logger.log_ask_complete(_complete_record())
    logger.log_ask_failure(
        AskAuditFailure(request_id="r", question_length=1, error_message="fail"),
    )
    logger.log_llm_usage(
        LLMUsageAuditRecord(
            request_id="r",
            provider="groq",
            model="m",
            latency_ms=1.0,
            total_tokens=1,
        ),
    )


def test_structlog_audit_emits_complete_event() -> None:
    settings = make_settings(
        observability_audit_enabled=True,
        observability_log_sql=False,
        observability_log_question=False,
    )
    audit = StructlogAuditLogger(settings)
    audit._logger = MagicMock()  # noqa: SLF001

    audit.log_ask_complete(_complete_record(sql_text="SELECT 1", question_text="secret?"))

    audit._logger.info.assert_called_once()
    args, kwargs = audit._logger.info.call_args
    assert args[0] == "ask_audit_complete"
    assert kwargs["token_usage"]["combined_total_tokens"] == 42
    assert "sql_text" not in kwargs
    assert "question_text" not in kwargs


def test_structlog_audit_includes_sql_when_enabled() -> None:
    settings = make_settings(
        observability_audit_enabled=True,
        observability_log_sql=True,
    )
    audit = StructlogAuditLogger(settings)
    audit._logger = MagicMock()  # noqa: SLF001

    audit.log_ask_complete(_complete_record(sql_text="SELECT COUNT(*) FROM t"))

    assert audit._logger.info.call_args[1]["sql_text"] == "SELECT COUNT(*) FROM t"


def test_structlog_audit_logs_llm_usage() -> None:
    settings = make_settings(
        observability_audit_enabled=True,
        observability_llm_usage_enabled=True,
    )
    audit = StructlogAuditLogger(settings)
    audit._logger = MagicMock()  # noqa: SLF001

    audit.log_llm_usage(
        LLMUsageAuditRecord(
            request_id="req-2",
            provider="groq",
            model="llama-test",
            latency_ms=120.5,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            task="sql_generation",
        ),
    )

    args, kwargs = audit._logger.info.call_args
    assert args[0] == "llm_usage"
    assert kwargs["total_tokens"] == 150
    assert kwargs["task"] == "sql_generation"


def test_structlog_audit_disabled_by_settings() -> None:
    settings = make_settings(observability_audit_enabled=False)
    audit = StructlogAuditLogger(settings)
    audit._logger = MagicMock()  # noqa: SLF001

    audit.log_ask_complete(_complete_record())

    audit._logger.info.assert_not_called()
