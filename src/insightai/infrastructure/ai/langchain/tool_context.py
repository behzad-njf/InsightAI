"""Mutable context captured by LangChain agent tools (Phase 10.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from insightai.domain.models.hybrid import RAGRetrievalResult
from insightai.domain.models.query_execution import RunQueryResult
from insightai.domain.models.sql_generation import GenerateSQLResult


@dataclass
class LangChainAgentToolContext:
    """Side effects from agent tool calls used to build ``AskResult``."""

    tools_used: list[str] = field(default_factory=list)
    rag_retrieval: RAGRetrievalResult | None = None
    sql: GenerateSQLResult | None = None
    execution: RunQueryResult | None = None

    def record_tool(self, name: str) -> None:
        if name not in self.tools_used:
            self.tools_used.append(name)
