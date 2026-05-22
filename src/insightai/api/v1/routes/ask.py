"""Ask pipeline routes (Phase 6.5 debug API)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from insightai.api.auth.dependencies import get_governance_context
from insightai.api.deps import get_ask_use_case
from insightai.api.schemas.ask import AskRequest, AskResponse
from insightai.application.use_cases.ask import AskUseCase

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(
    request: Request,
    body: AskRequest,
    use_case: AskUseCase = Depends(get_ask_use_case),
) -> AskResponse:
    """
    Answer a natural language question using the full read-only pipeline.

    Flow: schema context → SQL generation → validate → execute → NL answer.
    Requires a configured readonly database (``INSIGHTAI_DATABASE_READONLY_URL``).
    """
    result = await use_case.execute(
        body.to_domain(governance_context=get_governance_context(request)),
    )
    return AskResponse.from_domain(result)
