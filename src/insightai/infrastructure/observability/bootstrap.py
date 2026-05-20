"""Build observability components from settings."""

from __future__ import annotations

from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.observability.structlog_audit import (
    NullAuditLogger,
    StructlogAuditLogger,
)


def build_audit_logger(settings: Settings) -> StructlogAuditLogger | NullAuditLogger:
    """Return the configured audit logger implementation."""
    if not settings.observability_audit_enabled:
        return NullAuditLogger()
    return StructlogAuditLogger(settings)
