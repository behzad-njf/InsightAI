"""Product chat API (Phase 7) — NL question → grounded answer."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from insightai.api.audit_context import bind_chat_audit_context
from insightai.api.chat_session_resolve import resolve_chat_session_id
from insightai.api.deps import get_ask_use_case, get_chat_session_use_case, get_settings
from insightai.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    chat_stream_event_to_sse,
)
from insightai.api.sse import format_sse
from insightai.api.v1.routes import chat_sessions
from insightai.application.use_cases.ask import AskUseCase
from insightai.application.use_cases.chat_session import ChatSessionUseCase
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import request_id_var

router = APIRouter(prefix="/chat", tags=["chat"])
router.include_router(chat_sessions.router)

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _validate_question_length(question: str, settings: Settings) -> None:
    if len(question) > settings.chat_max_question_length:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": (
                    f"question exceeds maximum length of "
                    f"{settings.chat_max_question_length} characters."
                ),
            },
        )


@router.post("", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    use_case: AskUseCase = Depends(get_ask_use_case),
    session_use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """
    Answer a natural language question about your data.

    Runs the full read-only pipeline (schema → SQL → execute → summary).
    Use ``/api/v1/ask`` for debug payloads (token usage, full SQL metadata).
    """
    question = body.question.strip()
    _validate_question_length(question, settings)

    session_id = resolve_chat_session_id(request, body)
    if session_id:
        await session_use_case.require_session(session_id)
    bind_chat_audit_context(request, session_id=session_id)

    result = await use_case.execute(body.to_domain())

    if session_id:
        await session_use_case.record_exchange(
            session_id,
            question=question,
            result=result,
            request_id=request_id_var.get(),
            store_sql=body.include_sql,
        )

    response_request = body.model_copy(update={"session_id": session_id})
    return ChatResponse.from_domain(result, request=response_request)


@router.post("/stream")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    use_case: AskUseCase = Depends(get_ask_use_case),
    session_use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Stream a grounded answer via Server-Sent Events (SSE).

    Events: ``status`` → ``token`` (answer deltas) → ``done`` (full payload) or ``error``.

    Same auth and rate limits as ``POST /chat``. Session history is recorded on ``done``.

    Disable with ``INSIGHTAI_CHAT_STREAMING_ENABLED=false``.
    """
    if not settings.chat_streaming_enabled:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": (
                    "Chat streaming is disabled. Set INSIGHTAI_CHAT_STREAMING_ENABLED=true "
                    "or use POST /api/v1/chat."
                ),
            },
        )

    question = body.question.strip()
    _validate_question_length(question, settings)

    session_id = resolve_chat_session_id(request, body)
    if session_id:
        await session_use_case.require_session(session_id)
    bind_chat_audit_context(request, session_id=session_id)

    response_request = body.model_copy(update={"session_id": session_id})

    async def event_generator() -> AsyncIterator[str]:
        async for stream_event in use_case.execute_stream(body.to_domain()):
            if stream_event.kind == "done" and stream_event.result is not None and session_id:
                await session_use_case.record_exchange(
                    session_id,
                    question=question,
                    result=stream_event.result,
                    request_id=request_id_var.get(),
                    store_sql=body.include_sql,
                )
            event_name, data = chat_stream_event_to_sse(
                stream_event,
                request=response_request,
            )
            yield format_sse(event_name, data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )
