"""Unit tests for answer prompt row sampling (Phase 6.3)."""

from __future__ import annotations

import pytest

from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.infrastructure.prompts.result_format import format_query_result_for_prompt
from insightai.infrastructure.prompts.result_sampling import (
    sample_rows_for_prompt,
    sampling_footnote,
)


def _rows(n: int) -> list[dict[str, int]]:
    return [{"id": i} for i in range(n)]


def test_sample_all_when_under_cap() -> None:
    sample = sample_rows_for_prompt(_rows(5), max_rows=10)
    assert sample.was_sampled is False
    assert sample.strategy == "all"
    assert sample.displayed_count == 5
    assert [r["id"] for r in sample.rows] == [0, 1, 2, 3, 4]


def test_sample_head_tail_spread_when_over_cap() -> None:
    sample = sample_rows_for_prompt(_rows(100), max_rows=10)
    assert sample.was_sampled is True
    assert sample.strategy == "head_tail_spread"
    assert sample.displayed_count == 10
    ids = [r["id"] for r in sample.rows]
    assert ids[0] == 0
    assert ids[-1] == 99
    assert len(set(ids)) == 10


def test_sample_includes_middle_rows() -> None:
    sample = sample_rows_for_prompt(_rows(200), max_rows=12)
    ids = {r["id"] for r in sample.rows}
    assert 0 in ids
    assert 199 in ids
    assert any(50 <= i <= 150 for i in ids)


def test_sample_max_rows_one() -> None:
    sample = sample_rows_for_prompt(_rows(50), max_rows=1)
    assert sample.displayed_count == 1
    assert sample.rows[0]["id"] == 0


def test_sample_invalid_max_raises() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        sample_rows_for_prompt(_rows(3), max_rows=0)


def test_sampling_footnote_only_when_sampled() -> None:
    all_rows = sample_rows_for_prompt(_rows(3), max_rows=10)
    assert sampling_footnote(all_rows, total_row_count=3) == ""

    spread = sample_rows_for_prompt(_rows(20), max_rows=5)
    note = sampling_footnote(spread, total_row_count=20)
    assert "Sampled 5 of 20" in note
    assert "evenly spaced" in note


def test_format_query_result_uses_sampling_footnote() -> None:
    result = QueryResult(
        columns=[QueryColumn(name="id")],
        rows=_rows(30),
        row_count=30,
    )
    table = format_query_result_for_prompt(result, max_display_rows=6)
    assert "Sampled 6 of 30" in table
    assert "| 0 |" in table
    assert "| 29 |" in table
