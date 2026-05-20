"""LangChain agent models (Phase 10.5)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from insightai.domain.models.hybrid import RAGRetrievalResult  # noqa: TC001
from insightai.domain.models.query_execution import RunQueryResult  # noqa: TC001
from insightai.domain.models.sql_generation import GenerateSQLResult  # noqa: TC001


class LangChainAgentRunResult(BaseModel):
    """Outcome of a LangChain tool-calling agent run."""

    question: str
    answer: str
    tools_used: list[str] = Field(default_factory=list)
    rag_retrieval: RAGRetrievalResult | None = None
    sql: GenerateSQLResult | None = None
    execution: RunQueryResult | None = None
    agent_ms: float = Field(default=0.0, ge=0.0)

    model_config = {"frozen": True}
