"""SQL safety port — read-only enforcement foundation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.sql import SQLValidationResult


class ISQLSafetyValidator(ABC):
    """
    Validates that SQL is read-only before execution.

    Phase 1: keyword blocklist + statement prefix checks.
    Phase 4: sqlglot AST parsing via ``SQLParseValidator``; production wiring uses
    ``CompositeSQLValidator`` (AST authoritative, keyword fail-closed fallback).
    """

    @abstractmethod
    def validate(self, sql: str) -> SQLValidationResult:
        """
        Validate SQL without executing it.

        Returns:
            SQLValidationResult with is_valid=False and violations populated on failure.
        """

    def assert_readonly(self, sql: str) -> SQLValidationResult:
        """
        Validate and raise ReadOnlySQLViolationError on failure.

        Convenience for executors; implemented as default to avoid duplication.
        """
        from insightai.domain.exceptions import ReadOnlySQLViolationError

        result = self.validate(sql)
        if not result.is_valid:
            reason = "; ".join(result.violations) or "SQL is not allowed."
            raise ReadOnlySQLViolationError(
                reason,
                sql=sql,
                reason=reason,
            )
        return result
