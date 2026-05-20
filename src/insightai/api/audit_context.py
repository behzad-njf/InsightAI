"""Bind request-scoped audit metadata for chat and ask routes."""

from __future__ import annotations

from fastapi import Request

from insightai.domain.models.auth import AuthenticatedPrincipal
from insightai.infrastructure.observability.context import bind_audit_context


def bind_chat_audit_context(request: Request, *, session_id: str | None) -> None:
    """Attach session and authenticated principal to audit log context."""
    principal = getattr(request.state, "principal", None)
    auth_subject: str | None = None
    if isinstance(principal, AuthenticatedPrincipal):
        auth_subject = principal.subject
    bind_audit_context(session_id=session_id, auth_subject=auth_subject)
