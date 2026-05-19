"""Product chat API schemas (Phase 7.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from insightai.domain.models.ask import AskRequest as DomainAskRequest
from insightai.domain.models.ask import AskResult, AskStreamEvent, AskStreamPhase
from insightai.infrastructure.logging.setup import request_id_var


class ChatRequest(BaseModel):
    """Product chat request — one natural language question per call (Phase 7)."""

    question: str = Field(min_length=1, description="Natural language question.")
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Session from POST /chat/sessions; also accepted via X-Session-ID header.",
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    include_sql: bool = Field(
        default=False,
        description="Include generated SQL in the response (debug / power users).",
    )
    include_data: bool = Field(
        default=False,
        description="Include query result rows in the response.",
    )

    def to_domain(self) -> DomainAskRequest:
        return DomainAskRequest(
            question=self.question.strip(),
            timeout_seconds=self.timeout_seconds,
        )


class ChatTimingsSchema(BaseModel):
    """Latency breakdown in milliseconds."""

    sql_generation_ms: float
    query_execution_ms: float
    answer_generation_ms: float
    total_ms: float


class ChatDataSchema(BaseModel):
    """Optional tabular payload when ``include_data`` is true."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


class ChatResponse(BaseModel):
    """Product chat response — grounded answer with optional SQL/data."""

    question: str
    answer: str
    summary_bullets: list[str] = Field(default_factory=list)
    caveats: str | None = None
    row_count: int
    truncation_noted: bool
    request_id: str
    session_id: str | None = None
    timings: ChatTimingsSchema
    sql: str | None = None
    data: ChatDataSchema | None = None

    @classmethod
    def from_domain(
        cls,
        result: AskResult,
        *,
        request: ChatRequest,
    ) -> ChatResponse:
        request_id = request_id_var.get() or "unknown"
        columns = [col.name for col in result.execution.query_result.columns]
        data: ChatDataSchema | None = None
        if request.include_data:
            data = ChatDataSchema(
                columns=columns,
                rows=result.execution.query_result.rows,
                row_count=result.execution.query_result.row_count,
                truncated=result.execution.query_result.truncated,
            )
        sql: str | None = None
        if request.include_sql:
            sql = result.execution.sql

        return cls(
            question=result.question,
            answer=result.answer.answer.answer,
            summary_bullets=result.answer.answer.summary_bullets,
            caveats=result.answer.answer.caveats,
            row_count=result.execution.query_result.row_count,
            truncation_noted=result.answer.answer.truncation_noted,
            request_id=request_id,
            session_id=request.session_id,
            timings=ChatTimingsSchema(
                sql_generation_ms=result.timings.sql_generation_ms,
                query_execution_ms=result.timings.query_execution_ms,
                answer_generation_ms=result.timings.answer_generation_ms,
                total_ms=result.timings.total_ms,
            ),
            sql=sql,
            data=data,
        )


class ChatStreamStatusSchema(BaseModel):
    """SSE ``status`` event payload."""

    phase: str


class ChatStreamTokenSchema(BaseModel):
    """SSE ``token`` event payload."""

    text: str


class ChatStreamErrorSchema(BaseModel):
    """SSE ``error`` event payload."""

    error_message: str
    error_code: str | None = None
    request_id: str


def chat_stream_event_to_sse(event: AskStreamEvent, *, request: ChatRequest) -> tuple[str, dict[str, Any]]:
    """
    Map a domain stream event to SSE ``(event_name, data_dict)``.

    ``done`` uses the same JSON shape as ``ChatResponse``.
    """
    request_id = request_id_var.get() or "unknown"

    if event.kind == "status" and event.phase is not None:
        return (
            "status",
            ChatStreamStatusSchema(phase=event.phase.value).model_dump(),
        )
    if event.kind == "token" and event.text:
        return ("token", ChatStreamTokenSchema(text=event.text).model_dump())
    if event.kind == "done" and event.result is not None:
        response = ChatResponse.from_domain(event.result, request=request)
        return ("done", response.model_dump())
    if event.kind == "error":
        return (
            "error",
            ChatStreamErrorSchema(
                error_message=event.error_message or "Unknown error",
                error_code=event.error_code,
                request_id=request_id,
            ).model_dump(),
        )
    return ("error", ChatStreamErrorSchema(
        error_message="Invalid stream event",
        error_code="internal_error",
        request_id=request_id,
    ).model_dump())
