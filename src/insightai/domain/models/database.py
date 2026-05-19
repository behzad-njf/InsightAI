"""Database domain models — dialect-agnostic connection and result types."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — required at runtime for Pydantic fields
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DatabaseKind(StrEnum):
    """Supported database engines (config: INSIGHTAI_DATABASE_KIND)."""

    MSSQL = "mssql"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class DatabaseConnectionConfig(BaseModel):
    """Resolved connection parameters for engine factory (Step 5)."""

    kind: DatabaseKind
    url: str = Field(description="SQLAlchemy URL including driver and credentials.")
    readonly: bool = Field(
        default=True,
        description="True when this connection is for AI query execution only.",
    )
    pool_size: int = Field(default=5, ge=1, le=50)
    pool_timeout_seconds: int = Field(default=30, ge=1)
    echo_sql: bool = False

    @field_validator("url")
    @classmethod
    def url_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Database URL must not be empty."
            raise ValueError(msg)
        return stripped

    model_config = {"frozen": True}


class QueryExecutionOptions(BaseModel):
    """Safety limits applied at execution time (Phase 4–5 enforce)."""

    max_rows: int = Field(default=1000, ge=1, le=100_000)
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    enforce_readonly: bool = True

    model_config = {"frozen": True}


class QueryColumn(BaseModel):
    """Column metadata for a result set."""

    name: str
    type_name: str | None = None

    model_config = {"frozen": True}


class QueryResult(BaseModel):
    """Normalized read-only query result."""

    columns: list[QueryColumn]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool = Field(
        default=False,
        description="True when results were capped by max_rows.",
    )
    execution_time_ms: float | None = None
    executed_at: datetime | None = None

    model_config = {"frozen": True}

    @property
    def is_empty(self) -> bool:
        return self.row_count == 0


class DatabaseHealthStatus(BaseModel):
    """Result of a database connectivity check."""

    healthy: bool
    kind: DatabaseKind
    latency_ms: float | None = None
    message: str | None = None

    model_config = {"frozen": True}
