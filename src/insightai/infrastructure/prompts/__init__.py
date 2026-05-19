"""File-based prompt templates (Phase 3+)."""

from insightai.infrastructure.prompts.loader import (
    SQLGenerationPromptBundle,
    dialect_label,
    load_sql_generation_prompts,
    render_sql_generation_messages,
)

__all__ = [
    "SQLGenerationPromptBundle",
    "dialect_label",
    "load_sql_generation_prompts",
    "render_sql_generation_messages",
]
