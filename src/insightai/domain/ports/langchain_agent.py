"""LangChain agent port (Phase 10.5)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.langchain_agent import LangChainAgentRunResult


class ILangChainAgentRunner(ABC):
    """Run a tool-calling agent over InsightAI SQL + RAG capabilities."""

    @abstractmethod
    async def run(self, question: str) -> LangChainAgentRunResult:
        """
        Invoke the configured LangChain agent with document search and SQL tools.

        Read-only SQL safety is enforced inside the SQL tool (same path as ``AskUseCase``).
        """
