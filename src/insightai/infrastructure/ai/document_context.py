"""Append hybrid RAG context to LLM message lists (Phase 10.4)."""

from __future__ import annotations

from insightai.domain.models.llm import LLMMessage, LLMRole

_DOCUMENT_SECTION_HEADER = "\n\n## Reference documents (semantic search)\n\n"


def append_document_context_to_messages(
    messages: list[LLMMessage],
    document_context: str | None,
) -> list[LLMMessage]:
    """Extend the last user message with retrieved document excerpts."""
    if not document_context or not document_context.strip():
        return messages
    if not messages:
        return messages

    last = messages[-1]
    if last.role != LLMRole.USER:
        return messages

    updated_user = LLMMessage(
        role=LLMRole.USER,
        content=last.content + _DOCUMENT_SECTION_HEADER + document_context.strip(),
    )
    return [*messages[:-1], updated_user]
