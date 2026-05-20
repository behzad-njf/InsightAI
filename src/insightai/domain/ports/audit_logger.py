"""Port for structured ask-pipeline audit events (Phase 8.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from insightai.domain.models.audit import (
        AskAuditComplete,
        AskAuditFailure,
        LLMUsageAuditRecord,
    )


class IAuditLogger(Protocol):
    """Emit redacted, policy-aware audit records for product ask requests."""

    def log_ask_complete(self, record: AskAuditComplete) -> None:
        """Record a successful NL → SQL → execute → answer run."""

    def log_ask_failure(self, record: AskAuditFailure) -> None:
        """Record a failed ask or chat stream run."""

    def log_llm_usage(self, record: LLMUsageAuditRecord) -> None:
        """Record token usage for one LLM provider call."""
