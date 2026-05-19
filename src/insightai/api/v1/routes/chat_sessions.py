"""Chat session CRUD and message history (Phase 7.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from insightai.api.deps import get_chat_session_use_case
from insightai.api.schemas.chat_session import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
)
from insightai.application.use_cases.chat_session import ChatSessionUseCase
from insightai.domain.exceptions import ChatSessionNotFoundError

router = APIRouter(prefix="/sessions", tags=["chat-sessions"])


@router.post("", response_model=ChatSessionResponse, status_code=201)
async def create_chat_session(
    body: CreateChatSessionRequest | None = None,
    use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
) -> ChatSessionResponse:
    """Create a new conversation session. Use the returned ``id`` on ``POST /chat``."""
    title = body.title if body else None
    session = await use_case.create(title=title)
    return ChatSessionResponse.from_domain(session)


@router.get("/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: str,
    use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
) -> ChatSessionResponse:
    session = await use_case.get(session_id)
    return ChatSessionResponse.from_domain(session)


@router.delete("/{session_id}", status_code=204, response_class=Response)
async def delete_chat_session(
    session_id: str,
    use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
) -> Response:
    deleted = await use_case.delete(session_id)
    if not deleted:
        raise ChatSessionNotFoundError(session_id)
    return Response(status_code=204)


@router.get("/{session_id}/messages", response_model=ChatMessageListResponse)
async def list_chat_messages(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    use_case: ChatSessionUseCase = Depends(get_chat_session_use_case),
) -> ChatMessageListResponse:
    session = await use_case.get(session_id)
    messages = await use_case.list_messages(session_id, limit=limit, offset=offset)
    return ChatMessageListResponse(
        session_id=session_id,
        messages=[ChatMessageResponse.from_domain(m) for m in messages],
        total=session.message_count,
    )
