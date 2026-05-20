"""Load RAG answer prompts (Phase 10.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightai.domain.exceptions import PromptNotFoundError
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.prompts.loader import _read_prompt_file, prompts_root

_RAG_DIR = "rag"
_SYSTEM_FILE = "system.md"
_USER_FILE = "user.md"
_STREAM_SYSTEM_FILE = "stream_system.md"
_STREAM_USER_FILE = "stream_user.md"


def rag_prompts_dir(settings: Settings | None = None) -> Path:
    return prompts_root(settings) / _RAG_DIR


@dataclass(frozen=True)
class RAGAnswerPromptBundle:
    """Loaded RAG answer system + user templates."""

    system_template: str
    user_template: str

    def render_system(self) -> str:
        return self.system_template

    def render_user(self, *, question: str, document_excerpts: str) -> str:
        return self.user_template.format(
            question=question.strip(),
            document_excerpts=document_excerpts.strip(),
        )


def load_rag_answer_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> RAGAnswerPromptBundle:
    directory = prompts_dir or rag_prompts_dir(settings)
    return RAGAnswerPromptBundle(
        system_template=_read_prompt_file(directory / _SYSTEM_FILE),
        user_template=_read_prompt_file(directory / _USER_FILE),
    )


def load_rag_answer_stream_prompts(
    settings: Settings | None = None,
    *,
    prompts_dir: Path | None = None,
) -> RAGAnswerPromptBundle:
    directory = prompts_dir or rag_prompts_dir(settings)
    try:
        return RAGAnswerPromptBundle(
            system_template=_read_prompt_file(directory / _STREAM_SYSTEM_FILE),
            user_template=_read_prompt_file(directory / _STREAM_USER_FILE),
        )
    except PromptNotFoundError:
        return load_rag_answer_prompts(settings, prompts_dir=directory)
