"""Build LLM usage audit records (Phase 8.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.audit import LLMUsageAuditRecord
from insightai.domain.models.llm import LLMRequest, LLMResponse, TokenUsage
from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.context import get_audit_context

if TYPE_CHECKING:
    from insightai.domain.models.llm import LLMStreamChunk


def _task_from_request(request: LLMRequest) -> str | None:
    task = request.metadata.get("task")
    if isinstance(task, str) and task.strip():
        return task.strip()
    return None


def build_llm_usage_record(
    *,
    request: LLMRequest,
    provider: str,
    model: str,
    usage: TokenUsage,
    latency_ms: float,
    stream: bool,
    finish_reason: str | None = None,
) -> LLMUsageAuditRecord:
    ctx = get_audit_context()
    request_id = request_id_var.get() or "unknown"
    return LLMUsageAuditRecord(
        request_id=request_id,
        provider=provider,
        model=model,
        latency_ms=round(latency_ms, 2),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        task=_task_from_request(request),
        stream=stream,
        finish_reason=finish_reason,
        session_id=ctx.session_id if ctx else None,
        auth_subject=ctx.auth_subject if ctx else None,
    )


def build_llm_usage_from_response(
    *,
    request: LLMRequest,
    response: LLMResponse,
    latency_ms: float,
    stream: bool,
) -> LLMUsageAuditRecord:
    return build_llm_usage_record(
        request=request,
        provider=response.provider.value,
        model=response.model,
        usage=response.usage,
        latency_ms=latency_ms,
        stream=stream,
        finish_reason=response.finish_reason,
    )


def terminal_stream_usage(chunks: list[LLMStreamChunk]) -> tuple[TokenUsage, str | None]:
    """Extract usage and finish_reason from the last metadata chunk in a stream."""
    usage = TokenUsage()
    finish_reason: str | None = None
    for chunk in reversed(chunks):
        if finish_reason is None and chunk.finish_reason:
            finish_reason = chunk.finish_reason
        if chunk.usage is not None and chunk.usage.has_usage:
            usage = chunk.usage
            break
    return usage, finish_reason
