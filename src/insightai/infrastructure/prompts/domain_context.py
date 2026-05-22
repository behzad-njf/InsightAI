"""Format optional knowledge-base excerpts for SQL generation prompts."""

from __future__ import annotations

_DOMAIN_SECTION_HEADER = (
    "## Domain guidance (knowledge base — use with schema context; "
    "table/column names must still appear in schema context)\n\n"
)


def format_domain_context_section(domain_context: str | None) -> str:
    """Render the user-prompt block for retrieved Knowledge documents, or empty."""
    text = (domain_context or "").strip()
    if not text:
        return ""
    return f"{_DOMAIN_SECTION_HEADER}{text}\n"
