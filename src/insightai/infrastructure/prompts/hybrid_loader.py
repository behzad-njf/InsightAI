"""Load hybrid SQL + RAG answer prompts (Phase 10.6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightai.domain.models.database import QueryResult
from insightai.domain.models.llm import LLMMessage, LLMRole
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.prompts.loader import _read_prompt_file, prompts_root
from insightai.infrastructure.prompts.result_format import (
    column_names_list,
    format_query_result_for_prompt,
)

_HYBRID_DIR = "hybrid"
_COMBINED_SYSTEM = "combined_system.md"
_COMBINED_USER = "combined_user.md"
_COMBINED_STREAM_SYSTEM = "combined_stream_system.md"
_COMBINED_STREAM_USER = "combined_stream_user.md"


def hybrid_prompts_dir(settings: Settings | None = None) -> Path:
    return prompts_root(settings) / _HYBRID_DIR


@dataclass(frozen=True)
class HybridAnswerPromptBundle:
    """Combined SQL + document answer templates."""

    system_template: str
    user_template: str

    def render_system(self) -> str:
        return self.system_template

    def render_user(
        self,
        *,
        question: str,
        sql: str,
        query_result: QueryResult,
        max_display_rows: int,
        document_excerpts: str,
    ) -> str:
        result_table = format_query_result_for_prompt(
            query_result,
            max_display_rows=max_display_rows,
        )
        return self.user_template.format(
            question=question.strip(),
            sql=sql.strip(),
            row_count=query_result.row_count,
            truncated="yes" if query_result.truncated else "no",
            column_names=column_names_list(query_result),
            result_table=result_table,
            document_excerpts=document_excerpts.strip(),
        )


def load_hybrid_answer_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> HybridAnswerPromptBundle:
    directory = prompts_dir or hybrid_prompts_dir(settings)
    return HybridAnswerPromptBundle(
        system_template=_read_prompt_file(directory / _COMBINED_SYSTEM),
        user_template=_read_prompt_file(directory / _COMBINED_USER),
    )


def load_hybrid_answer_stream_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> HybridAnswerPromptBundle:
    directory = prompts_dir or hybrid_prompts_dir(settings)
    return HybridAnswerPromptBundle(
        system_template=_read_prompt_file(directory / _COMBINED_STREAM_SYSTEM),
        user_template=_read_prompt_file(directory / _COMBINED_STREAM_USER),
    )


def render_hybrid_answer_messages(
    *,
    question: str,
    sql: str,
    query_result: QueryResult,
    document_excerpts: str,
    max_display_rows: int | None = None,
    settings: Settings | None = None,
    bundle: HybridAnswerPromptBundle | None = None,
) -> list[LLMMessage]:
    """Build LLM messages for a combined SQL + RAG answer."""
    settings = settings or get_settings()
    row_limit = (
        max_display_rows if max_display_rows is not None else settings.answer_max_prompt_rows
    )
    prompts = bundle or load_hybrid_answer_prompts(settings)
    return [
        LLMMessage(role=LLMRole.SYSTEM, content=prompts.render_system()),
        LLMMessage(
            role=LLMRole.USER,
            content=prompts.render_user(
                question=question,
                sql=sql,
                query_result=query_result,
                max_display_rows=row_limit,
                document_excerpts=document_excerpts,
            ),
        ),
    ]
