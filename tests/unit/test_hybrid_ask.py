"""Hybrid ask pipeline tests (Phase 10.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.ask import AskUseCase
from insightai.application.use_cases.classify_query_route import ClassifyQueryRouteUseCase
from insightai.application.use_cases.generate_rag_answer import GenerateRAGAnswerUseCase
from insightai.application.use_cases.hybrid_ask import HybridAskUseCase
from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
from insightai.domain.models.answer import (
    AnswerGenerationResult,
    GenerateAnswerResult,
)
from insightai.domain.models.ask import AskRequest, AskResult, AskTimings
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.explainability import ExplainabilityPayload
from insightai.domain.models.hybrid import (
    QueryRouteKind,
    RAGRetrievalResult,
    RAGSourceCitation,
)
from insightai.infrastructure.rag.heuristic_router import HeuristicQueryRouter
from tests.conftest import make_settings
from tests.unit.test_ask_use_case import _answer_result, _run_result, _sql_result


def _rag_retrieval() -> RAGRetrievalResult:
    return RAGRetrievalResult(
        question="What is the campus policy?",
        sources=[
            RAGSourceCitation(
                id="chunk-1",
                source_path="docs/policy.md",
                chunk_index=0,
                text="Late pickup requires notifying the front desk.",
                score=0.88,
                section="Pickup",
            ),
        ],
        top_k=5,
        retrieval_ms=12.0,
    )


def _rag_answer() -> GenerateAnswerResult:
    empty = QueryResult(
        columns=[QueryColumn(name="_rag")],
        rows=[],
        row_count=0,
        executed_at=datetime.now(UTC),
        truncated=False,
    )
    return GenerateAnswerResult(
        question="What is the campus policy?",
        sql="",
        query_result=empty,
        answer=AnswerGenerationResult(
            answer="Late pickup requires notifying the front desk [1].",
            row_count=0,
            truncation_noted=False,
        ),
    )


@pytest.fixture
def hybrid_ask() -> HybridAskUseCase:
    sql_ask = MagicMock(spec=AskUseCase)
    sql_ask.execute_sql_pipeline = AsyncMock(
        return_value=AskResult(
            question="How many children?",
            route=QueryRouteKind.SQL,
            sql=_sql_result(),
            execution=_run_result(),
            answer=_answer_result(),
            timings=AskTimings(
                sql_generation_ms=1.0,
                query_execution_ms=2.0,
                answer_generation_ms=3.0,
                total_ms=6.0,
            ),
            explainability=ExplainabilityPayload(
                question="How many children?",
                route=QueryRouteKind.SQL,
            ),
        ),
    )

    retrieve = MagicMock(spec=RetrieveRAGContextUseCase)
    retrieve.execute = AsyncMock(return_value=_rag_retrieval())

    rag_answer = MagicMock(spec=GenerateRAGAnswerUseCase)
    rag_answer.execute = AsyncMock(return_value=_rag_answer())

    generate_answer = MagicMock()
    generate_answer.execute = AsyncMock(return_value=_answer_result())

    router = HeuristicQueryRouter()
    return HybridAskUseCase(
        sql_ask,
        ClassifyQueryRouteUseCase(router),
        retrieve,
        rag_answer,
        generate_answer,
        settings=make_settings(rag_enabled=True),
        audit=MagicMock(),
    )


@pytest.mark.asyncio
async def test_hybrid_ask_rag_route_skips_sql(hybrid_ask: HybridAskUseCase) -> None:
    result = await hybrid_ask.execute(
        AskRequest(
            question="What is the campus policy on late pickup?",
            route=QueryRouteKind.RAG,
        ),
    )

    assert result.route == QueryRouteKind.RAG
    assert result.sql is None
    assert result.execution is None
    assert result.rag_retrieval is not None
    assert result.rag_retrieval.has_sources
    assert result.explainability is not None
    assert result.explainability.route == QueryRouteKind.RAG
    hybrid_ask._sql_ask.execute_sql_pipeline.assert_not_called()  # type: ignore[attr-defined]
    hybrid_ask._generate_rag_answer.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hybrid_ask_sql_route_delegates(hybrid_ask: HybridAskUseCase) -> None:
    result = await hybrid_ask.execute(
        AskRequest(
            question="How many children per classroom?",
            route=QueryRouteKind.SQL,
        ),
    )

    assert result.route == QueryRouteKind.SQL
    assert result.explainability is not None
    assert result.explainability.route == QueryRouteKind.SQL
    hybrid_ask._sql_ask.execute_sql_pipeline.assert_awaited_once()  # type: ignore[attr-defined]
    hybrid_ask._retrieve_rag.execute.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hybrid_ask_both_route_retrieves_and_runs_sql(hybrid_ask: HybridAskUseCase) -> None:
    result = await hybrid_ask.execute(
        AskRequest(
            question="According to policy, how many staff per classroom?",
            route=QueryRouteKind.BOTH,
        ),
    )

    assert result.route == QueryRouteKind.BOTH
    assert result.sql is not None
    assert result.execution is not None
    assert result.rag_retrieval is not None
    assert result.explainability is not None
    assert result.explainability.route == QueryRouteKind.BOTH
    hybrid_ask._sql_ask.execute_sql_pipeline.assert_awaited_once()  # type: ignore[attr-defined]
    hybrid_ask._retrieve_rag.execute.assert_awaited_once()  # type: ignore[attr-defined]
    hybrid_ask._generate_answer.execute.assert_awaited_once()  # type: ignore[attr-defined]
    answer_request = hybrid_ask._generate_answer.execute.await_args.args[0]  # type: ignore[attr-defined]
    assert answer_request.document_context is not None
