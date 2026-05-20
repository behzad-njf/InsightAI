"""AskUseCase audit integration (Phase 8.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.ask import AskUseCase
from insightai.domain.models.ask import AskRequest, AskStreamPhase

if TYPE_CHECKING:
    from insightai.domain.models.audit import AskAuditComplete, AskAuditFailure
from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.context import bind_audit_context, clear_audit_context
from tests.conftest import make_settings
from tests.unit.test_ask_use_case import (
    _answer_result,
    _run_result,
    _sql_result,
)


class RecordingAuditLogger:
    def __init__(self) -> None:
        self.complete: list[AskAuditComplete] = []
        self.failures: list[AskAuditFailure] = []

    def log_ask_complete(self, record: AskAuditComplete) -> None:
        self.complete.append(record)

    def log_ask_failure(self, record: AskAuditFailure) -> None:
        self.failures.append(record)

    def log_llm_usage(self, record: object) -> None:
        return


@pytest.fixture
def audited_ask_use_case() -> tuple[AskUseCase, RecordingAuditLogger]:
    generate_sql = MagicMock()
    generate_sql.execute = AsyncMock(return_value=_sql_result())
    run_query = MagicMock()
    run_query.execute = MagicMock(return_value=_run_result())
    generate_answer = MagicMock()
    generate_answer.execute = AsyncMock(return_value=_answer_result())
    audit = RecordingAuditLogger()
    use_case = AskUseCase(
        generate_sql,
        run_query,
        generate_answer,
        settings=make_settings(),
        audit=audit,
    )
    return use_case, audit


@pytest.mark.asyncio
async def test_execute_emits_audit_complete_with_request_and_session(
    audited_ask_use_case: tuple[AskUseCase, RecordingAuditLogger],
) -> None:
    use_case, audit = audited_ask_use_case
    rid_token = request_id_var.set("trace-abc")
    audit_token = bind_audit_context(session_id="sess-1", auth_subject="user@test")
    try:
        await use_case.execute(AskRequest(question="How many rows?"))
    finally:
        clear_audit_context(audit_token)
        request_id_var.reset(rid_token)

    assert len(audit.complete) == 1
    record = audit.complete[0]
    assert record.request_id == "trace-abc"
    assert record.session_id == "sess-1"
    assert record.auth_subject == "user@test"
    assert record.question_length == len("How many rows?")
    assert not audit.failures


@pytest.mark.asyncio
async def test_execute_stream_failure_emits_audit_failure(
    audited_ask_use_case: tuple[AskUseCase, RecordingAuditLogger],
) -> None:
    use_case, audit = audited_ask_use_case
    use_case._generate_sql.execute = AsyncMock(return_value=_sql_result(has_sql=False))  # type: ignore[method-assign]
    request_id_var.set("trace-err")

    events = [
        event
        async for event in use_case.execute_stream(AskRequest(question="Unknown metric?"))
    ]

    assert events[-1].kind == "error"
    assert len(audit.failures) == 1
    assert audit.failures[0].error_code == "sql_generation_error"
    assert audit.failures[0].phase == AskStreamPhase.GENERATING_SQL.value
    assert audit.failures[0].stream is True
