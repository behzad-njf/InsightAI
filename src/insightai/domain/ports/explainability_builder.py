"""Explainability builder port (Phase 13.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from insightai.domain.models.explainability import (
        ExplainabilityBuildRequest,
        ExplainabilityPayload,
    )


class IExplainabilityBuilder(Protocol):
    """
    Assemble ``ExplainabilityPayload`` from pipeline artifacts.

    Infrastructure implements this in step 13.2; ask/chat use cases invoke it in 13.3.
    """

    def build(self, request: ExplainabilityBuildRequest) -> ExplainabilityPayload:
        """
        Build a complete explainability payload for one ask/chat turn.

        Implementations must sanitize messages (no stack traces, connection strings,
        or raw LLM chain-of-thought).
        """
