"""Citation helpers for hybrid document + SQL answers (Phase 10.6)."""

from __future__ import annotations

import re

from insightai.domain.models.answer import AnswerGenerationResult, GenerateAnswerResult
from insightai.domain.models.hybrid import RAGSourceCitation

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_bracket_citations(answer_text: str) -> list[int]:
    """Return unique 1-based citation indices found in prose (e.g. ``[1]``, ``[2]``)."""
    indices = {int(match.group(1)) for match in _CITATION_PATTERN.finditer(answer_text)}
    return sorted(indices)


def resolve_citations(
    *,
    answer_text: str,
    llm_citations: list[int] | None,
    source_count: int,
) -> list[int]:
    """
    Merge LLM-declared citations with bracket markers in the answer.

    Drops out-of-range indices. Returns sorted unique 1-based indices.
    """
    if source_count <= 0:
        return []

    merged: set[int] = set()
    if llm_citations:
        merged.update(llm_citations)
    merged.update(extract_bracket_citations(answer_text))
    return sorted(index for index in merged if 1 <= index <= source_count)


def enrich_generate_answer_result(
    result: GenerateAnswerResult,
    sources: list[RAGSourceCitation],
) -> GenerateAnswerResult:
    """Attach document sources and resolved citation indices to an answer."""
    if not sources:
        return result

    citations = resolve_citations(
        answer_text=result.answer.answer,
        llm_citations=result.answer.citations,
        source_count=len(sources),
    )
    enriched_answer = result.answer.model_copy(update={"citations": citations})
    return result.model_copy(update={"sources": list(sources), "answer": enriched_answer})


def enrich_answer_generation_result(
    result: AnswerGenerationResult,
    sources: list[RAGSourceCitation],
) -> AnswerGenerationResult:
    """Attach citation indices to a standalone ``AnswerGenerationResult``."""
    if not sources:
        return result
    citations = resolve_citations(
        answer_text=result.answer,
        llm_citations=result.citations,
        source_count=len(sources),
    )
    return result.model_copy(update={"citations": citations})
