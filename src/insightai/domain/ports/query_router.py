"""Query routing port — SQL vs RAG vs both (Phase 10.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.hybrid import RouteClassification


class IQueryRouter(ABC):
    """Classify a natural-language question into an execution route."""

    @abstractmethod
    def classify(self, question: str) -> RouteClassification:
        """
        Decide whether to use SQL analytics, document retrieval, or both.

        Implementations may use heuristics or an LLM; must not execute SQL or search vectors.
        """
