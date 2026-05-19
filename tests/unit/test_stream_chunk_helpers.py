"""Unit tests for shared LLM stream chunk helpers."""

from __future__ import annotations

from types import SimpleNamespace

from insightai.infrastructure.ai.providers.base import (
    iter_sdk_stream_chunks,
    terminal_stream_metadata,
)


def test_iter_sdk_stream_chunks_text_and_terminal() -> None:
    events = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="x"), finish_reason=None)],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
    ]
    chunks = list(iter_sdk_stream_chunks(events))
    assert [c.text for c in chunks if c.text] == ["x"]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None


def test_terminal_stream_metadata_reads_last_terminal_chunk() -> None:
    from insightai.domain.models.llm import LLMStreamChunk, TokenUsage

    chunks = [
        LLMStreamChunk(text="hi"),
        LLMStreamChunk(finish_reason="stop", usage=TokenUsage(total_tokens=5)),
    ]
    finish_reason, usage = terminal_stream_metadata(chunks)
    assert finish_reason == "stop"
    assert usage.total_tokens == 5
