"""Row sampling for answer-generation prompts (Phase 6.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SampledRows:
    """Rows selected for inclusion in the LLM prompt."""

    rows: list[dict[str, Any]]
    total_available: int
    displayed_count: int
    was_sampled: bool
    strategy: str

    @property
    def omitted_count(self) -> int:
        return max(0, self.total_available - self.displayed_count)


def sample_rows_for_prompt(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
) -> SampledRows:
    """
    Select up to ``max_rows`` rows for the answer prompt.

    When the result exceeds the cap, uses **head + tail + evenly spaced middle**
    so the model sees variety across the full range (not only the first rows).
    """
    if max_rows < 1:
        msg = "max_rows must be at least 1."
        raise ValueError(msg)

    total = len(rows)
    if total == 0:
        return SampledRows(
            rows=[],
            total_available=0,
            displayed_count=0,
            was_sampled=False,
            strategy="empty",
        )
    if total <= max_rows:
        return SampledRows(
            rows=list(rows),
            total_available=total,
            displayed_count=total,
            was_sampled=False,
            strategy="all",
        )

    indices = _head_tail_spread_indices(total, max_rows)
    sampled = [rows[i] for i in indices]
    return SampledRows(
        rows=sampled,
        total_available=total,
        displayed_count=len(sampled),
        was_sampled=True,
        strategy="head_tail_spread",
    )


def sampling_footnote(sample: SampledRows, *, total_row_count: int) -> str:
    """Human-readable note when rows were sampled for the prompt."""
    if not sample.was_sampled:
        return ""

    total = total_row_count if total_row_count >= sample.total_available else sample.total_available
    return (
        f"\n(Sampled {sample.displayed_count} of {total} rows for this prompt: "
        "first rows, last rows, and evenly spaced rows in between.)"
    )


def _head_tail_spread_indices(total: int, max_rows: int) -> list[int]:
    """Pick unique sorted indices covering head, tail, and spread middle."""
    if total <= max_rows:
        return list(range(total))

    head = max(1, max_rows // 3)
    tail = max(1, max_rows // 3)
    middle_slots = max_rows - head - tail

    indices: list[int] = list(range(head))
    middle_start = head
    middle_end = total - tail - 1
    if middle_slots > 0 and middle_end >= middle_start:
        indices.extend(_even_indices(middle_start, middle_end, middle_slots))
    indices.extend(range(total - tail, total))

    return sorted(set(indices))[:max_rows]


def _even_indices(start: int, end: int, count: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [(start + end) // 2]
    span = end - start
    if span <= 0:
        return [start] * count
    return [start + round(i * span / (count - 1)) for i in range(count)]
