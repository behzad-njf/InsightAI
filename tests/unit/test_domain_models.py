"""Unit tests for domain models and SQL safety port defaults."""

from __future__ import annotations

import pytest

from insightai.domain.exceptions import ReadOnlySQLViolationError
from insightai.domain.models.llm import LLMMessage, LLMRequest, LLMRole
from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.ports.sql_safety import ISQLSafetyValidator


class _RejectAllValidator(ISQLSafetyValidator):
    def validate(self, sql: str) -> SQLValidationResult:
        return SQLValidationResult(
            is_valid=False,
            statement_kind=SQLStatementKind.FORBIDDEN,
            violations=["blocked"],
        )


def test_llm_request_requires_messages() -> None:
    with pytest.raises(ValueError):
        LLMRequest(messages=[])


def test_llm_request_accepts_valid_messages() -> None:
    req = LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content="Hello")],
    )
    assert len(req.messages) == 1


def test_sql_validation_result_readonly_select() -> None:
    ok = SQLValidationResult(is_valid=True, statement_kind=SQLStatementKind.SELECT)
    assert ok.is_readonly_select is True

    bad = SQLValidationResult(is_valid=True, statement_kind=SQLStatementKind.FORBIDDEN)
    assert bad.is_readonly_select is False


def test_assert_readonly_raises() -> None:
    validator = _RejectAllValidator()
    with pytest.raises(ReadOnlySQLViolationError):
        validator.assert_readonly("DELETE FROM accounts_user")
