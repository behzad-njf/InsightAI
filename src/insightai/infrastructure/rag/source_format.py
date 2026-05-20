"""Format retrieved RAG chunks for LLM prompts (Phase 10.4)."""

from __future__ import annotations

from insightai.domain.models.hybrid import RAGRetrievalResult, RAGSourceCitation


def format_rag_sources_for_prompt(retrieval: RAGRetrievalResult) -> str:
    """Render citations as numbered excerpts for answer / hybrid prompts."""
    if not retrieval.sources:
        return "(No document excerpts matched the question.)"

    blocks: list[str] = []
    for index, source in enumerate(retrieval.sources, start=1):
        header = _source_header(index, source)
        blocks.append(f"{header}\n{source.text.strip()}")
    return "\n\n".join(blocks)


def _source_header(index: int, source: RAGSourceCitation) -> str:
    location = source.source_path
    if source.section:
        location = f"{location} — {source.section}"
    title = f" ({source.title})" if source.title else ""
    return f"[{index}] {location}{title} (relevance={source.score:.3f})"
