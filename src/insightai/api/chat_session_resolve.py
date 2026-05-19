"""Resolve chat session id from request body or headers."""

from __future__ import annotations

from fastapi import HTTPException, Request

from insightai.api.schemas.chat import ChatRequest


def resolve_chat_session_id(request: Request, body: ChatRequest) -> str | None:
    """
    Return session id from JSON body or ``X-Session-ID`` header.

    Raises 400 when both are set and differ.
    """
    header_id = request.headers.get("X-Session-ID", "").strip() or None
    body_id = body.session_id.strip() if body.session_id else None
    if header_id and body_id and header_id != body_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "session_id_mismatch",
                "message": "session_id in body does not match X-Session-ID header.",
            },
        )
    return body_id or header_id
