"""Request-scoped audit context (session, auth subject)."""

from __future__ import annotations

from contextvars import ContextVar, Token

from insightai.domain.models.audit import AuditContext

audit_context_var: ContextVar[AuditContext | None] = ContextVar(
    "audit_context",
    default=None,
)


def bind_audit_context(
    *,
    session_id: str | None = None,
    auth_subject: str | None = None,
    api_key_id: str | None = None,
) -> Token[AuditContext | None]:
    """
    Merge audit metadata for the current request.

    Call from auth (subject) and chat routes (session_id). Returns a token for
    ``clear_audit_context`` when scoping a sub-operation.
    """
    current = audit_context_var.get()
    merged = AuditContext(
        session_id=session_id or (current.session_id if current else None),
        auth_subject=auth_subject or (current.auth_subject if current else None),
        api_key_id=api_key_id or (current.api_key_id if current else None),
    )
    return audit_context_var.set(merged)


def clear_audit_context(token: Token[AuditContext | None]) -> None:
    """Restore a previous audit context token."""
    audit_context_var.reset(token)


def get_audit_context() -> AuditContext | None:
    return audit_context_var.get()
