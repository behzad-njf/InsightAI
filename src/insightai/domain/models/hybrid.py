"""Hybrid SQL + RAG routing models (Phase 10.4)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from insightai.domain.models.rag import VectorSearchResult  # noqa: TC001


class QueryRouteKind(StrEnum):
    """How a natural-language question should be answered."""

    SQL = "sql"
    RAG = "rag"
    BOTH = "both"
    AGENT = "agent"
    AUTO = "auto"


class RouteClassification(BaseModel):
    """Outcome of classifying a question before running pipelines."""

    route: QueryRouteKind
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    sql_signals: int = Field(default=0, ge=0)
    rag_signals: int = Field(default=0, ge=0)

    model_config = {"frozen": True}


class RAGSourceCitation(BaseModel):
    """One retrieved document chunk exposed to the user or answer LLM."""

    id: str
    source_path: str
    chunk_index: int
    text: str
    score: float = Field(ge=0.0, le=1.0)
    title: str | None = None
    section: str | None = None

    model_config = {"frozen": True}

    @classmethod
    def from_search_result(cls, hit: VectorSearchResult) -> RAGSourceCitation:
        return cls(
            id=hit.id,
            source_path=hit.source_path,
            chunk_index=hit.chunk_index,
            text=hit.text,
            score=hit.score,
            title=hit.title,
            section=hit.section,
        )


class RAGRetrievalResult(BaseModel):
    """Vector search hits for a user question."""

    question: str
    sources: list[RAGSourceCitation] = Field(default_factory=list)
    top_k: int = Field(ge=1)
    retrieval_ms: float = Field(default=0.0, ge=0.0)

    model_config = {"frozen": True}

    @property
    def has_sources(self) -> bool:
        return bool(self.sources)
