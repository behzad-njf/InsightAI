"""Port for the full NL → SQL → execute → answer pipeline (Phase 7.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from insightai.domain.models.ask import AskRequest, AskResult, AskStreamEvent


class IAskPipeline(Protocol):
    """
    Orchestrate schema context → SQL → validate → execute → answer.

    Implemented by ``AskUseCase``; product APIs (``/chat``) depend on this port.
    """

    async def execute(self, request: AskRequest) -> AskResult:
        """Run the read-only analytics pipeline for one question."""

    def execute_stream(self, request: AskRequest) -> AsyncIterator[AskStreamEvent]:
        """Stream status, answer tokens, and a terminal ``done`` or ``error`` event."""
