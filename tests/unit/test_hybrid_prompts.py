"""Hybrid combined answer prompts (Phase 10.6)."""

from __future__ import annotations

from datetime import UTC, datetime

from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.infrastructure.prompts.hybrid_loader import render_hybrid_answer_messages


def test_render_hybrid_answer_messages_includes_documents_and_sql() -> None:
    query_result = QueryResult(
        columns=[QueryColumn(name="count")],
        rows=[{"count": 2}],
        row_count=1,
        executed_at=datetime.now(UTC),
        truncated=False,
    )
    messages = render_hybrid_answer_messages(
        question="How many classrooms per policy?",
        sql="SELECT COUNT(*) FROM school_classroom",
        query_result=query_result,
        document_excerpts="[1] campus.md\nEach site needs two classrooms.",
        max_display_rows=10,
    )
    user_content = messages[1].content
    assert "Document excerpts" in user_content
    assert "campus.md" in user_content
    assert "SELECT COUNT" in user_content
    assert messages[0].content  # system prompt
