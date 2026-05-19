"""Shared helpers for LLM provider adapters."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from insightai.domain.models.llm import LLMStreamChunk, TokenUsage


def token_usage_from_payload(usage: Any) -> TokenUsage:
    """Build TokenUsage from OpenAI/Groq-style usage objects or dicts."""
    if usage is None:
        return TokenUsage()
    if isinstance(usage, dict):
        return TokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    return TokenUsage(
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


def provider_error_message(exc: Exception) -> str:
    """Extract a useful message from nested SDK exceptions."""
    return str(exc).strip() or exc.__class__.__name__


def iter_sdk_stream_chunks(chunks: Any) -> Iterator[LLMStreamChunk]:
    """
    Map OpenAI/Groq-style chat completion stream events to domain chunks.

    Yields text deltas as they arrive, then a terminal chunk with
    ``finish_reason`` / ``usage`` when present on the stream.
    """
    finish_reason: str | None = None
    usage: TokenUsage | None = None

    for chunk in chunks:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is not None:
            content = getattr(delta, "content", None)
            if content:
                yield LLMStreamChunk(text=content)
        if getattr(choice, "finish_reason", None):
            finish_reason = choice.finish_reason
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            parsed = token_usage_from_payload(chunk_usage)
            if parsed.has_usage:
                usage = parsed

    if finish_reason is not None or usage is not None:
        yield LLMStreamChunk(finish_reason=finish_reason, usage=usage)


def terminal_stream_metadata(chunks: list[LLMStreamChunk]) -> tuple[str | None, TokenUsage]:
    """Read ``finish_reason`` and ``usage`` from the last terminal stream chunk."""
    finish_reason: str | None = None
    usage = TokenUsage()
    for chunk in reversed(chunks):
        if chunk.finish_reason is not None:
            finish_reason = chunk.finish_reason
        if chunk.usage is not None:
            usage = chunk.usage
        if finish_reason is not None and chunk.usage is not None:
            break
    return finish_reason, usage
