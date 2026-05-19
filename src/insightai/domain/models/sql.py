"""SQL safety domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SQLStatementKind(StrEnum):
    """High-level SQL statement classification."""

    SELECT = "select"
    UNKNOWN = "unknown"
    FORBIDDEN = "forbidden"


class SQLValidationResult(BaseModel):
    """Outcome of read-only SQL validation."""

    is_valid: bool
    statement_kind: SQLStatementKind = SQLStatementKind.UNKNOWN
    normalized_sql: str | None = None
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @property
    def is_readonly_select(self) -> bool:
        return self.is_valid and self.statement_kind == SQLStatementKind.SELECT
