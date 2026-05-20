"""Hybrid query router tests (Phase 10.4)."""

from __future__ import annotations

import pytest

from insightai.application.use_cases.classify_query_route import ClassifyQueryRouteUseCase
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.infrastructure.rag.heuristic_router import HeuristicQueryRouter


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How many children are enrolled per classroom?", QueryRouteKind.SQL),
        ("What is the campus policy on late pickup?", QueryRouteKind.RAG),
        (
            "According to the handbook, how many staff are required per classroom?",
            QueryRouteKind.BOTH,
        ),
    ],
)
def test_heuristic_router_classifies_examples(question: str, expected: QueryRouteKind) -> None:
    router = HeuristicQueryRouter()
    decision = router.classify(question)
    assert decision.route == expected


def test_classify_use_case_honors_forced_route() -> None:
    use_case = ClassifyQueryRouteUseCase(HeuristicQueryRouter())
    decision = use_case.execute(
        "How many rows?",
        requested_route=QueryRouteKind.RAG,
    )
    assert decision.route == QueryRouteKind.RAG
    assert decision.confidence == 1.0
