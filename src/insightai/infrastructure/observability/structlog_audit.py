"""Structlog-backed audit logger (Phase 8.1)."""

from __future__ import annotations

from insightai.domain.models.audit import AskAuditComplete, AskAuditFailure, LLMUsageAuditRecord
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

_AUDIT_LOGGER_NAME = "insightai.audit"


class NullAuditLogger:
    """No-op audit sink when observability is disabled."""

    def log_ask_complete(self, record: AskAuditComplete) -> None:
        return

    def log_ask_failure(self, record: AskAuditFailure) -> None:
        return

    def log_llm_usage(self, record: LLMUsageAuditRecord) -> None:
        return


class StructlogAuditLogger:
    """
    Emit ``ask_audit_*`` events via structlog.

    SQL and question text are omitted unless explicitly enabled in settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(_AUDIT_LOGGER_NAME)

    @property
    def enabled(self) -> bool:
        return self._settings.observability_audit_enabled

    def log_ask_complete(self, record: AskAuditComplete) -> None:
        if not self.enabled:
            return
        payload = self._complete_payload(record)
        self._logger.info("ask_audit_complete", **payload)

    def log_ask_failure(self, record: AskAuditFailure) -> None:
        if not self.enabled:
            return
        payload = record.model_dump(mode="json", exclude_none=True)
        self._logger.info("ask_audit_failure", **payload)

    def log_llm_usage(self, record: LLMUsageAuditRecord) -> None:
        if not self._llm_usage_enabled:
            return
        payload = record.model_dump(mode="json", exclude_none=True)
        self._logger.info("llm_usage", **payload)

    @property
    def _llm_usage_enabled(self) -> bool:
        return self.enabled and self._settings.observability_llm_usage_enabled

    def _complete_payload(self, record: AskAuditComplete) -> dict[str, object]:
        payload = record.model_dump(mode="json", exclude_none=True)
        if not self._settings.observability_log_sql:
            payload.pop("sql_text", None)
        if not self._settings.observability_log_question:
            payload.pop("question_text", None)
        return payload
