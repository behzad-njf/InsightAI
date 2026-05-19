"""Format ``QueryResult`` for LLM answer-generation prompts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from insightai.infrastructure.prompts.result_sampling import (
    sample_rows_for_prompt,
    sampling_footnote,
)

if TYPE_CHECKING:
    from insightai.domain.models.database import QueryResult


def format_query_result_for_prompt(
    result: QueryResult,
    *,
    max_display_rows: int,
) -> str:
    """
    Render result rows as a markdown table for the answer prompt.

    Large sets are sampled (head, tail, evenly spaced middle) — see ``result_sampling``.
    """
    if result.row_count == 0 or not result.rows:
        return "(No rows returned.)"

    columns = [col.name for col in result.columns]
    if not columns:
        return "(No columns in result.)"

    sample = sample_rows_for_prompt(result.rows, max_rows=max_display_rows)
    lines = [
        "| " + " | ".join(_escape_cell(name) for name in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in sample.rows:
        lines.append(
            "| " + " | ".join(_escape_cell(_cell_value(row, name)) for name in columns) + " |",
        )

    footnote = sampling_footnote(sample, total_row_count=result.row_count)
    if footnote:
        lines.append(footnote)
    elif sample.omitted_count > 0:
        lines.append(
            f"\n(Showing {sample.displayed_count} of {result.row_count} rows; "
            f"{sample.omitted_count} more omitted from prompt.)",
        )

    if result.truncated:
        lines.append(
            "\n(Executor truncated results at the configured row limit; "
            "the database may contain additional matching rows.)",
        )

    return "\n".join(lines)


def column_names_list(result: QueryResult) -> str:
    """Comma-separated column names for prompt metadata."""
    if not result.columns:
        return "(none)"
    return ", ".join(col.name for col in result.columns)


def _cell_value(row: dict[str, Any], column: str) -> Any:
    if column in row:
        return row[column]
    return ""


def _escape_cell(value: Any) -> str:
    """Escape pipe characters and newlines for markdown tables."""
    if value is None:
        return ""
    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")
