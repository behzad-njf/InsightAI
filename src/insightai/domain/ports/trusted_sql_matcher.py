"""Trusted SQL matcher port — map questions/SQL to approved assets (Phase 11)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.semantic import (
        SemanticCatalog,
        TrustedSQLMatchRequest,
        TrustedSQLMatchResult,
    )


class ITrustedSQLMatcher(ABC):
    """Match NL questions or SQL text against a loaded semantic catalog."""

    @abstractmethod
    def match(
        self,
        request: TrustedSQLMatchRequest,
        catalog: SemanticCatalog,
    ) -> TrustedSQLMatchResult:
        """
        Return a trusted asset when SQL or question matches an approved entry.

        Non-matches return ``TrustedSQLMatchResult.no_match()`` for LLM fallthrough.
        """
