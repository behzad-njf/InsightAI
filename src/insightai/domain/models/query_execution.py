"""Query execution domain models — validated SQL → result set (Phase 5)."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from insightai.domain.models.database import QueryExecutionOptions, QueryResult
from insightai.domain.models.sql_generation import (  # noqa: TC001
    GenerateSQLResult,
    SQLGenerationResult,
)


class RunQuerySQLSource(StrEnum):
    """How the SQL text was supplied to the run-query use case."""

    RAW = "raw"
    GENERATED = "generated"


class RunQueryRequest(BaseModel):
    """
    Execute a read-only SQL query.

    Provide exactly one of: ``sql``, ``generated_sql``, or ``generate_result``.
    """

    sql: str | None = Field(
        default=None,
        description="Raw SQL to validate and execute.",
    )
    generated_sql: SQLGenerationResult | None = Field(
        default=None,
        description="Phase 3 SQL generation output.",
    )
    generate_result: GenerateSQLResult | None = Field(
        default=None,
        description="Full Phase 3 pipeline result (uses ``generate_result.sql``).",
    )
    max_rows: int | None = Field(default=None, ge=1, le=100_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    enforce_readonly: bool | None = Field(
        default=None,
        description="When None, uses settings.sql_enforce_readonly.",
    )

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_sql_source(self) -> Self:
        sources = int(self._has_raw_sql()) + int(self._has_generated_sql())
        if sources == 0:
            msg = "Provide one of: sql, generated_sql, or generate_result with non-empty SQL."
            raise ValueError(msg)
        if sources > 1:
            msg = "Provide only one SQL source (sql, generated_sql, or generate_result)."
            raise ValueError(msg)
        return self

    def resolve_sql(self) -> str:
        """Return the SQL string to execute."""
        if self.sql is not None:
            text = self.sql.strip()
            if not text:
                msg = "SQL must not be empty."
                raise ValueError(msg)
            return text

        generation = self._generation_result()
        if generation is None or not generation.has_sql:
            msg = "Generated SQL is empty."
            raise ValueError(msg)
        return generation.sql.strip()

    def sql_source(self) -> RunQuerySQLSource:
        if self.sql is not None and self.sql.strip():
            return RunQuerySQLSource.RAW
        return RunQuerySQLSource.GENERATED

    def resolved_generation(self) -> SQLGenerationResult | None:
        if self.sql_source() == RunQuerySQLSource.RAW:
            return None
        return self._generation_result()

    def _has_raw_sql(self) -> bool:
        return self.sql is not None and bool(self.sql.strip())

    def _has_generated_sql(self) -> bool:
        generation = self._generation_result()
        return generation is not None and generation.has_sql

    def _generation_result(self) -> SQLGenerationResult | None:
        if self.generate_result is not None:
            return self.generate_result.sql
        return self.generated_sql

    @classmethod
    def from_sql(
        cls,
        sql: str,
        *,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
        enforce_readonly: bool | None = None,
    ) -> Self:
        return cls(
            sql=sql,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
            enforce_readonly=enforce_readonly,
        )

    @classmethod
    def from_generation(
        cls,
        generated: SQLGenerationResult,
        *,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
        enforce_readonly: bool | None = None,
    ) -> Self:
        return cls(
            generated_sql=generated,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
            enforce_readonly=enforce_readonly,
        )

    @classmethod
    def from_generate_sql(
        cls,
        result: GenerateSQLResult,
        *,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
        enforce_readonly: bool | None = None,
    ) -> Self:
        return cls(
            generate_result=result,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
            enforce_readonly=enforce_readonly,
        )

    def to_execution_options(
        self,
        defaults: QueryExecutionOptions,
    ) -> QueryExecutionOptions:
        """Merge request overrides with settings defaults."""
        return QueryExecutionOptions(
            max_rows=self.max_rows if self.max_rows is not None else defaults.max_rows,
            timeout_seconds=(
                self.timeout_seconds
                if self.timeout_seconds is not None
                else defaults.timeout_seconds
            ),
            enforce_readonly=(
                self.enforce_readonly
                if self.enforce_readonly is not None
                else defaults.enforce_readonly
            ),
        )


class RunQueryResult(BaseModel):
    """Outcome of executing a read-only query."""

    sql: str = Field(description="SQL executed (post-validation normalization).")
    source: RunQuerySQLSource
    query_result: QueryResult
    question: str | None = Field(
        default=None,
        description="Original NL question when source is generated SQL.",
    )
    generation: SQLGenerationResult | None = Field(
        default=None,
        description="Attached when execution used Phase 3 output.",
    )
    execution_options: QueryExecutionOptions = Field(
        description="Limits applied for this run (from settings + request overrides).",
    )

    model_config = {"frozen": True}
