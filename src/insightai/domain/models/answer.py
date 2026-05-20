"""Answer generation domain models — question + SQL + rows → natural language."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from insightai.domain.models.database import QueryResult  # noqa: TC001
from insightai.domain.models.hybrid import RAGSourceCitation  # noqa: TC001
from insightai.domain.models.llm import LLMProviderKind, TokenUsage
from insightai.domain.models.query_execution import RunQueryResult  # noqa: TC001


class AnswerGenerationRequest(BaseModel):
    """Input for summarizing a read-only query result (Phase 6)."""

    question: str = Field(min_length=1, description="Original user question.")
    sql: str = Field(min_length=1, description="Executed read-only SQL.")
    query_result: QueryResult = Field(description="Rows returned from execution.")
    max_display_rows: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Max rows embedded in the LLM prompt; defaults when None.",
    )
    model: str | None = Field(default=None, description="Optional LLM model override.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    document_context: str | None = Field(
        default=None,
        description="Formatted RAG excerpts for hybrid BOTH answers (Phase 10.4).",
    )

    model_config = {"frozen": True}

    @classmethod
    def from_run_query(
        cls,
        run: RunQueryResult,
        *,
        question: str | None = None,
        max_display_rows: int | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        document_context: str | None = None,
    ) -> Self:
        """Build from Phase 5 execution output."""
        resolved_question = (question or run.question or "").strip()
        if not resolved_question:
            msg = "question is required when RunQueryResult has no question."
            raise ValueError(msg)
        return cls(
            question=resolved_question,
            sql=run.sql.strip(),
            query_result=run.query_result,
            max_display_rows=max_display_rows,
            model=model,
            temperature=temperature,
            document_context=document_context,
        )


class AnswerGenerationLLMOutput(BaseModel):
    """Parsed JSON from the LLM (see ``prompts/answer_generation/system.md``)."""

    answer: str = ""
    summary_bullets: list[str] = Field(default_factory=list)
    row_count_cited: int = Field(ge=0)
    truncation_noted: bool = False
    caveats: str | None = None
    source_citations: list[int] = Field(
        default_factory=list,
        description="1-based indices of document excerpts cited (hybrid / RAG answers).",
    )

    model_config = {"frozen": True}


class AnswerGenerationResult(BaseModel):
    """Natural-language answer grounded in query results."""

    answer: str
    summary_bullets: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0, description="Authoritative row count from execution.")
    truncation_noted: bool = Field(
        description="True when truncation was communicated or results were capped.",
    )
    caveats: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model: str | None = None
    provider: LLMProviderKind | None = None
    finish_reason: str | None = None
    citations: list[int] = Field(
        default_factory=list,
        description="1-based indices into ``GenerateAnswerResult.sources`` cited in the answer.",
    )

    model_config = {"frozen": True}

    @classmethod
    def from_llm_output(
        cls,
        output: AnswerGenerationLLMOutput,
        *,
        query_result: QueryResult,
        usage: TokenUsage | None = None,
        model: str | None = None,
        provider: LLMProviderKind | None = None,
        finish_reason: str | None = None,
    ) -> Self:
        """Map parsed LLM JSON into a domain result; row count from execution."""
        truncation_noted = output.truncation_noted or query_result.truncated
        caveats = (output.caveats or "").strip() or None
        return cls(
            answer=output.answer.strip(),
            summary_bullets=list(output.summary_bullets),
            row_count=query_result.row_count,
            truncation_noted=truncation_noted,
            caveats=caveats,
            citations=list(output.source_citations),
            usage=usage or TokenUsage(),
            model=model,
            provider=provider,
            finish_reason=finish_reason,
        )

    @classmethod
    def from_streamed_text(
        cls,
        answer: str,
        *,
        query_result: QueryResult,
        usage: TokenUsage | None = None,
        model: str | None = None,
        provider: LLMProviderKind | None = None,
        finish_reason: str | None = None,
    ) -> Self:
        """Build a result from plain-prose streaming output (no JSON parse)."""
        return cls(
            answer=answer.strip(),
            summary_bullets=[],
            row_count=query_result.row_count,
            truncation_noted=query_result.truncated,
            caveats=None,
            usage=usage or TokenUsage(),
            model=model,
            provider=provider,
            finish_reason=finish_reason,
        )


class AnswerGenerationStreamChunk(BaseModel):
    """
    One event from ``IAnswerGenerator.generate_stream``.

    Yields ``text_delta`` events, then a single terminal chunk with ``result``.
    """

    kind: Literal["token", "done"] = "token"
    text_delta: str | None = None
    result: AnswerGenerationResult | None = None

    model_config = {"frozen": True}

    @classmethod
    def token(cls, text: str) -> Self:
        return cls(kind="token", text_delta=text)

    @classmethod
    def done(cls, result: AnswerGenerationResult) -> Self:
        return cls(kind="done", result=result)


class GenerateAnswerRequest(BaseModel):
    """End-to-end answer generation request (question + SQL + result rows)."""

    question: str = Field(min_length=1)
    sql: str | None = Field(
        default=None,
        description="SQL executed; required unless run_query_result is set.",
    )
    query_result: QueryResult | None = None
    run_query_result: RunQueryResult | None = None
    max_display_rows: int | None = Field(default=None, ge=1, le=500)
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    document_context: str | None = Field(
        default=None,
        description="Formatted RAG excerpts appended to the answer prompt (Phase 10.4).",
    )

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_result_source(self) -> Self:
        has_query = self.query_result is not None
        has_run = self.run_query_result is not None
        if has_query == has_run:
            msg = "Provide exactly one of query_result or run_query_result."
            raise ValueError(msg)
        if has_run and self.sql is not None and self.sql.strip():
            msg = "Do not set sql when run_query_result is provided."
            raise ValueError(msg)
        if has_query and not (self.sql or "").strip():
            msg = "sql is required when query_result is provided."
            raise ValueError(msg)
        return self

    def to_generation_request(self) -> AnswerGenerationRequest:
        if self.run_query_result is not None:
            return AnswerGenerationRequest.from_run_query(
                self.run_query_result,
                question=self.question,
                max_display_rows=self.max_display_rows,
                model=self.model,
                temperature=self.temperature,
                document_context=self.document_context,
            )
        assert self.query_result is not None
        assert self.sql is not None
        return AnswerGenerationRequest(
            question=self.question.strip(),
            sql=self.sql.strip(),
            query_result=self.query_result,
            max_display_rows=self.max_display_rows,
            model=self.model,
            temperature=self.temperature,
            document_context=self.document_context,
        )


class GenerateAnswerResult(BaseModel):
    """Question, SQL, execution snapshot, and generated answer."""

    question: str
    sql: str
    query_result: QueryResult
    answer: AnswerGenerationResult
    sources: list[RAGSourceCitation] = Field(
        default_factory=list,
        description="Retrieved document chunks when RAG or hybrid path ran.",
    )

    model_config = {"frozen": True}

    @classmethod
    def from_parts(
        cls,
        request: GenerateAnswerRequest,
        answer: AnswerGenerationResult,
        *,
        sources: list[RAGSourceCitation] | None = None,
    ) -> Self:
        gen = request.to_generation_request()
        return cls(
            question=gen.question,
            sql=gen.sql,
            query_result=gen.query_result,
            answer=answer,
            sources=list(sources or []),
        )


class GenerateAnswerStreamChunk(BaseModel):
    """One event from ``GenerateAnswerUseCase.execute_stream``."""

    kind: Literal["token", "done"] = "token"
    text_delta: str | None = None
    result: GenerateAnswerResult | None = None

    model_config = {"frozen": True}

    @classmethod
    def token(cls, text: str) -> Self:
        return cls(kind="token", text_delta=text)

    @classmethod
    def done(cls, result: GenerateAnswerResult) -> Self:
        return cls(kind="done", result=result)
