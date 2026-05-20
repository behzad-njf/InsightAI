"""Completion token cap tests."""

from __future__ import annotations

from insightai.infrastructure.ai.token_limits import cap_completion_tokens


def test_cap_completion_tokens_compound() -> None:
    assert cap_completion_tokens("groq/compound", 4096) == 1024
    assert cap_completion_tokens("groq/compound-mini", 512) == 512


def test_cap_completion_tokens_standard_model() -> None:
    assert cap_completion_tokens("llama-3.3-70b-versatile", 4096) == 4096
