"""Audit event models for observability (Phase 8.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from insightai.domain.models.ask import AskTimings


class AuditContext(BaseModel):
    """Request-scoped metadata bound before the ask pipeline runs."""

    session_id: str | None = None
    auth_subject: str | None = None
    api_key_id: str | None = None

    model_config = {"frozen": True}


class TokenUsageSummary(BaseModel):
    """Aggregated LLM token usage for one ask request."""

    sql_prompt_tokens: int | None = None
    sql_completion_tokens: int | None = None
    sql_total_tokens: int | None = None
    answer_prompt_tokens: int | None = None
    answer_completion_tokens: int | None = None
    answer_total_tokens: int | None = None
    combined_total_tokens: int | None = None

    model_config = {"frozen": True}


class AskAuditComplete(BaseModel):
    """Successful ask pipeline outcome for the audit log."""

    request_id: str
    question_length: int = Field(ge=0)
    session_id: str | None = None
    auth_subject: str | None = None
    auth_api_key_id: str | None = None
    auth_roles: list[str] = Field(default_factory=list)
    stream: bool = False
    schema_table_count: int = Field(ge=0)
    tables_used: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    truncated: bool = False
    timings: AskTimings
    token_usage: TokenUsageSummary = Field(default_factory=TokenUsageSummary)
    sql_model: str | None = None
    answer_model: str | None = None
    sql_provider: str | None = None
    answer_provider: str | None = None
    question_text: str | None = Field(
        default=None,
        description="Present only when INSIGHTAI_OBSERVABILITY_LOG_QUESTION=true.",
    )
    sql_text: str | None = Field(
        default=None,
        description="Present only when INSIGHTAI_OBSERVABILITY_LOG_SQL=true.",
    )
    route: str | None = Field(
        default=None,
        description="Hybrid route: sql | rag | both (Phase 10.4).",
    )
    rag_source_count: int = Field(
        default=0,
        ge=0,
        description="Number of document chunks retrieved for RAG / hybrid.",
    )
    governance_applied: bool = Field(
        default=False,
        description="True when Phase 12 governance modified the SQL.",
    )
    governance_dimensions_applied: list[str] = Field(
        default_factory=list,
        description="Scope dimension ids injected by governance.",
    )

    model_config = {"frozen": True}


class LLMUsageAuditRecord(BaseModel):
    """Per LLM completion (sync or stream terminal chunk)."""

    request_id: str
    provider: str
    model: str
    latency_ms: float = Field(ge=0.0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    task: str | None = Field(
        default=None,
        description="Logical task from LLMRequest.metadata (e.g. sql_generation).",
    )
    stream: bool = False
    finish_reason: str | None = None
    session_id: str | None = None
    auth_subject: str | None = None

    model_config = {"frozen": True}


class AskAuditFailure(BaseModel):
    """Failed ask pipeline outcome for the audit log."""

    request_id: str
    governance_denied: bool = Field(
        default=False,
        description="True when failure was caused by governance policy denial.",
    )
    question_length: int = Field(ge=0)
    error_message: str = Field(min_length=1)
    error_code: str | None = None
    session_id: str | None = None
    auth_subject: str | None = None
    stream: bool = False
    phase: str | None = Field(
        default=None,
        description="Pipeline stage when the failure was recorded, if known.",
    )

    model_config = {"frozen": True}
