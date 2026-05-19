"""Convert domain LLM messages to provider SDK formats."""

from __future__ import annotations

from insightai.domain.models.llm import LLMMessage


def to_chat_payload(messages: list[LLMMessage]) -> list[dict[str, str]]:
    """Map domain messages to OpenAI-compatible chat message dicts."""
    return [{"role": message.role.value, "content": message.content} for message in messages]
