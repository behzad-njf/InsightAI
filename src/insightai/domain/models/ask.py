"""End-to-end ask pipeline models — NL question → SQL → rows → answer (Phase 6.4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field

from insightai.domain.models.answer import GenerateAnswerResult  # noqa: TC001
from insightai.domain.models.database import DatabaseKind  # noqa: TC001
from insightai.domain.models.hybrid import QueryRouteKind, RAGRetrievalResult  # noqa: TC001
from insightai.domain.models.query_execution import RunQueryResult  # noqa: TC001
from insightai.domain.models.sql_generation import GenerateSQLResult  # noqa: TC001


class AskRequest(BaseModel):
    """Natural language question through the full read-only analytics pipeline."""

    question: str = Field(min_length=1)
    max_context_tables: int = Field(default=12, ge=1, le=50)
    max_rows: int | None = Field(
        default=None,
        ge=1,
        le=100_000,
        description="Row cap for generated SQL and query execution.",
    )
    database_kind: DatabaseKind | None = Field(
        default=None,
        description="SQL dialect override; uses settings when unset.",
    )
    sql_model: str | None = Field(default=None, description="LLM model for SQL generation.")
    sql_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    answer_model: str | None = Field(default=None, description="LLM model for answer generation.")
    answer_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_display_rows: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Max rows embedded in the answer prompt.",
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    enforce_readonly: bool | None = Field(default=None)
    route: QueryRouteKind | None = Field(
        default=None,
        description="Force sql | rag | both; None or auto uses hybrid router when RAG enabled.",
    )

    model_config = {"frozen": True}


class AskTimings(BaseModel):
    """Per-stage latency for the ask pipeline (milliseconds)."""

    route_classification_ms: float = Field(default=0.0, ge=0.0)
    rag_retrieval_ms: float = Field(default=0.0, ge=0.0)
    sql_generation_ms: float = Field(ge=0.0)
    query_execution_ms: float = Field(ge=0.0)
    answer_generation_ms: float = Field(ge=0.0)
    total_ms: float = Field(ge=0.0)

    model_config = {"frozen": True}


class AskResult(BaseModel):
    """Outcome of hybrid routing and one or both of SQL + RAG answer paths."""

    question: str
    route: QueryRouteKind = QueryRouteKind.SQL
    answer: GenerateAnswerResult
    timings: AskTimings
    sql: GenerateSQLResult | None = None
    execution: RunQueryResult | None = None
    rag_retrieval: RAGRetrievalResult | None = None

    model_config = {"frozen": True}


class AskStreamPhase(StrEnum):
    """Pipeline stage reported via ``AskStreamEvent.status``."""

    ROUTING = "routing"
    RETRIEVING_DOCUMENTS = "retrieving_documents"
    GENERATING_SQL = "generating_sql"
    EXECUTING_QUERY = "executing_query"
    GENERATING_ANSWER = "generating_answer"


class AskStreamEvent(BaseModel):
    """
    One event from ``IAskPipeline.execute_stream`` (SSE mapping in Phase 7).

    - ``status`` — phase started (SQL, query, or answer)
    - ``token`` — answer text delta
    - ``done`` — full ``AskResult`` with timings
    - ``error`` — pipeline failed; stream ends
    """

    kind: Literal["status", "token", "done", "error"]
    phase: AskStreamPhase | None = None
    text: str | None = None
    result: AskResult | None = None
    error_message: str | None = None
    error_code: str | None = None

    model_config = {"frozen": True}

    @classmethod
    def status(cls, phase: AskStreamPhase) -> Self:
        return cls(kind="status", phase=phase)

    @classmethod
    def token(cls, text: str) -> Self:
        return cls(kind="token", text=text)

    @classmethod
    def done(cls, result: AskResult) -> Self:
        return cls(kind="done", result=result)

    @classmethod
    def failure(cls, message: str, *, error_code: str | None = None) -> Self:
        return cls(kind="error", error_message=message, error_code=error_code)
