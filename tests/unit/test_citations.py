"""Citation resolution for hybrid answers (Phase 10.6)."""

from __future__ import annotations

from datetime import UTC, datetime

from insightai.api.schemas.chat import ChatRequest, build_chat_sources
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerResult,
)
from insightai.domain.models.ask import AskResult, AskTimings
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.hybrid import (
    QueryRouteKind,
    RAGRetrievalResult,
    RAGSourceCitation,
)
from insightai.infrastructure.rag.citations import (
    enrich_generate_answer_result,
    extract_bracket_citations,
    resolve_citations,
)


def test_extract_bracket_citations() -> None:
    text = "Per policy [1], late pickup requires notice. See also [2] and [1]."
    assert extract_bracket_citations(text) == [1, 2]


def test_resolve_citations_merges_llm_and_brackets() -> None:
    cited = resolve_citations(
        answer_text="Details in [2].",
        llm_citations=[1],
        source_count=3,
    )
    assert cited == [1, 2]


def test_enrich_generate_answer_result_attaches_sources() -> None:
    empty = QueryResult(
        columns=[QueryColumn(name="n")],
        rows=[],
        row_count=0,
        executed_at=datetime.now(UTC),
        truncated=False,
    )
    base = GenerateAnswerResult(
        question="Policy?",
        sql="",
        query_result=empty,
        answer=AnswerGenerationResult(
            answer="According to [1], notify the desk.",
            row_count=0,
            truncation_noted=False,
        ),
    )
    sources = [
        RAGSourceCitation(
            id="a",
            source_path="policy.md",
            chunk_index=0,
            text="Notify the desk.",
            score=0.9,
        ),
    ]
    enriched = enrich_generate_answer_result(base, sources)
    assert enriched.sources == sources
    assert enriched.answer.citations == [1]


def test_build_chat_sources_with_excerpts() -> None:
    retrieval = RAGRetrievalResult(
        question="Policy?",
        sources=[
            RAGSourceCitation(
                id="a",
                source_path="policy.md",
                chunk_index=0,
                text="Notify the desk.",
                score=0.88,
            ),
        ],
        top_k=5,
    )
    empty = QueryResult(
        columns=[QueryColumn(name="n")],
        rows=[],
        row_count=0,
        executed_at=datetime.now(UTC),
        truncated=False,
    )
    result = AskResult(
        question="Policy?",
        route=QueryRouteKind.RAG,
        answer=GenerateAnswerResult(
            question="Policy?",
            sql="",
            query_result=empty,
            answer=AnswerGenerationResult(
                answer="See [1] for pickup rules.",
                row_count=0,
                truncation_noted=False,
                citations=[1],
            ),
            sources=retrieval.sources,
        ),
        rag_retrieval=retrieval,
        timings=AskTimings(
            sql_generation_ms=0.0,
            query_execution_ms=0.0,
            answer_generation_ms=1.0,
            total_ms=1.0,
        ),
    )
    sources, citations = build_chat_sources(result, include_excerpts=True)
    assert len(sources) == 1
    assert sources[0].citation_index == 1
    assert sources[0].excerpt == "Notify the desk."
    assert citations == [1]

    response = ChatRequest(question="Policy?").model_dump()
    assert "include_source_excerpts" in response
