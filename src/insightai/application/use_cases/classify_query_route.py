"""Classify SQL vs RAG route for a question (Phase 10.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.hybrid import QueryRouteKind, RouteClassification

if TYPE_CHECKING:
    from insightai.domain.ports.query_router import IQueryRouter


class ClassifyQueryRouteUseCase:
    """Resolve the execution route for a natural-language question."""

    def __init__(self, router: IQueryRouter) -> None:
        self._router = router

    def execute(
        self,
        question: str,
        *,
        requested_route: QueryRouteKind | None = None,
    ) -> RouteClassification:
        """
        Classify ``question`` unless ``requested_route`` forces a path.

        ``QueryRouteKind.AUTO`` and ``None`` run the configured router.
        """
        if requested_route is not None and requested_route not in (
            QueryRouteKind.AUTO,
        ):
            return RouteClassification(
                route=requested_route,
                confidence=1.0,
                rationale="Route explicitly requested by caller.",
            )
        return self._router.classify(question)
