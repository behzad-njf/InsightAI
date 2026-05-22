"""Load and render prompt templates from the repository ``prompts/`` directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightai.domain.exceptions import PromptNotFoundError
from insightai.domain.models.database import DatabaseKind, QueryResult
from insightai.domain.models.llm import LLMMessage, LLMRole
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.prompts.domain_context import format_domain_context_section
from insightai.infrastructure.prompts.result_format import (
    column_names_list,
    format_query_result_for_prompt,
)

_SQL_GENERATION_DIR = "sql_generation"
_ANSWER_GENERATION_DIR = "answer_generation"
_SYSTEM_FILE = "system.md"
_USER_FILE = "user.md"
_STREAM_SYSTEM_FILE = "stream_system.md"
_STREAM_USER_FILE = "stream_user.md"

_DIALECT_LABELS: dict[DatabaseKind, str] = {
    DatabaseKind.MSSQL: "Microsoft SQL Server (T-SQL)",
    DatabaseKind.POSTGRESQL: "PostgreSQL",
    DatabaseKind.SQLITE: "SQLite",
}


def dialect_label(kind: DatabaseKind) -> str:
    """Human-readable dialect name for prompt injection."""
    return _DIALECT_LABELS.get(kind, kind.value)


def prompts_root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.project_root / "prompts"


def sql_generation_prompts_dir(settings: Settings | None = None) -> Path:
    return prompts_root(settings) / _SQL_GENERATION_DIR


def answer_generation_prompts_dir(settings: Settings | None = None) -> Path:
    return prompts_root(settings) / _ANSWER_GENERATION_DIR


def _read_prompt_file(path: Path) -> str:
    if not path.is_file():
        msg = f"Prompt file not found: {path}"
        raise PromptNotFoundError(msg)
    return path.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class SQLGenerationPromptBundle:
    """Loaded SQL generation system + user templates."""

    system_template: str
    user_template: str

    def render_system(self, *, sql_dialect: str, max_rows: int) -> str:
        return self.system_template.format(sql_dialect=sql_dialect, max_rows=max_rows)

    def render_user(
        self,
        *,
        question: str,
        schema_context: str,
        sql_dialect: str,
        max_rows: int,
        domain_context: str | None = None,
    ) -> str:
        return self.user_template.format(
            question=question.strip(),
            schema_context=schema_context.strip(),
            domain_context_section=format_domain_context_section(domain_context),
            sql_dialect=sql_dialect,
            max_rows=max_rows,
        )


def load_sql_generation_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> SQLGenerationPromptBundle:
    """Load ``prompts/sql_generation/system.md`` and ``user.md``."""
    directory = prompts_dir or sql_generation_prompts_dir(settings)
    return SQLGenerationPromptBundle(
        system_template=_read_prompt_file(directory / _SYSTEM_FILE),
        user_template=_read_prompt_file(directory / _USER_FILE),
    )


@dataclass(frozen=True)
class AnswerGenerationPromptBundle:
    """Loaded answer generation system + user templates (Phase 6.1)."""

    system_template: str
    user_template: str

    def render_system(self) -> str:
        return self.system_template

    def render_user(
        self,
        *,
        question: str,
        sql: str,
        row_count: int,
        truncated: bool,
        column_names: str,
        result_table: str,
    ) -> str:
        return self.user_template.format(
            question=question.strip(),
            sql=sql.strip(),
            row_count=row_count,
            truncated="yes" if truncated else "no",
            column_names=column_names,
            result_table=result_table.strip(),
        )


def load_answer_generation_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> AnswerGenerationPromptBundle:
    """Load ``prompts/answer_generation/system.md`` and ``user.md``."""
    directory = prompts_dir or answer_generation_prompts_dir(settings)
    return AnswerGenerationPromptBundle(
        system_template=_read_prompt_file(directory / _SYSTEM_FILE),
        user_template=_read_prompt_file(directory / _USER_FILE),
    )


def load_answer_generation_stream_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> AnswerGenerationPromptBundle:
    """Load ``stream_system.md`` and ``stream_user.md`` for token streaming (plain prose)."""
    directory = prompts_dir or answer_generation_prompts_dir(settings)
    return AnswerGenerationPromptBundle(
        system_template=_read_prompt_file(directory / _STREAM_SYSTEM_FILE),
        user_template=_read_prompt_file(directory / _STREAM_USER_FILE),
    )


def _render_answer_generation_messages_from_bundle(
    *,
    question: str,
    sql: str,
    query_result: QueryResult,
    max_display_rows: int,
    bundle: AnswerGenerationPromptBundle,
) -> list[LLMMessage]:
    result_table = format_query_result_for_prompt(
        query_result,
        max_display_rows=max_display_rows,
    )
    return [
        LLMMessage(role=LLMRole.SYSTEM, content=bundle.render_system()),
        LLMMessage(
            role=LLMRole.USER,
            content=bundle.render_user(
                question=question,
                sql=sql,
                row_count=query_result.row_count,
                truncated=query_result.truncated,
                column_names=column_names_list(query_result),
                result_table=result_table,
            ),
        ),
    ]


def render_answer_generation_messages(
    *,
    question: str,
    sql: str,
    query_result: QueryResult,
    max_display_rows: int | None = None,
    settings: Settings | None = None,
    bundle: AnswerGenerationPromptBundle | None = None,
) -> list[LLMMessage]:
    """
    Build system + user LLM messages for answer generation (Phase 6.1+).

    Loads prompt files on each call unless ``bundle`` is passed (cache at caller).
    """
    settings = settings or get_settings()
    row_limit = (
        max_display_rows if max_display_rows is not None else settings.answer_max_prompt_rows
    )
    prompts = bundle or load_answer_generation_prompts(settings)
    return _render_answer_generation_messages_from_bundle(
        question=question,
        sql=sql,
        query_result=query_result,
        max_display_rows=row_limit,
        bundle=prompts,
    )


def render_answer_generation_stream_messages(
    *,
    question: str,
    sql: str,
    query_result: QueryResult,
    max_display_rows: int | None = None,
    settings: Settings | None = None,
    bundle: AnswerGenerationPromptBundle | None = None,
) -> list[LLMMessage]:
    """
    Build LLM messages for streaming answer generation (plain prose, no JSON).

    Uses ``stream_system.md`` and ``stream_user.md`` unless ``bundle`` is provided.
    """
    settings = settings or get_settings()
    row_limit = (
        max_display_rows if max_display_rows is not None else settings.answer_max_prompt_rows
    )
    prompts = bundle or load_answer_generation_stream_prompts(settings)
    return _render_answer_generation_messages_from_bundle(
        question=question,
        sql=sql,
        query_result=query_result,
        max_display_rows=row_limit,
        bundle=prompts,
    )


def render_sql_generation_messages(
    *,
    question: str,
    schema_context: str,
    database_kind: DatabaseKind,
    max_rows: int | None = None,
    domain_context: str | None = None,
    settings: Settings | None = None,
    bundle: SQLGenerationPromptBundle | None = None,
) -> list[LLMMessage]:
    """
    Build system + user LLM messages for SQL generation (Phase 3.3+).

    Loads prompt files on each call unless ``bundle`` is passed (cache at caller).
    """
    settings = settings or get_settings()
    prompts = bundle or load_sql_generation_prompts(settings)
    dialect = dialect_label(database_kind)
    row_limit = max_rows if max_rows is not None else settings.sql_max_rows
    return [
        LLMMessage(
            role=LLMRole.SYSTEM,
            content=prompts.render_system(sql_dialect=dialect, max_rows=row_limit),
        ),
        LLMMessage(
            role=LLMRole.USER,
            content=prompts.render_user(
                question=question,
                schema_context=schema_context,
                sql_dialect=dialect,
                max_rows=row_limit,
                domain_context=domain_context,
            ),
        ),
    ]
