"""SQL generator port — natural language + schema context → read-only SQL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.sql_generation import (
        SQLGenerationRequest,
        SQLGenerationResult,
    )


class ISQLGenerator(ABC):
    """
    Generates a single read-only SQL statement from a question and schema context.

    Implementations load prompts from ``prompts/sql_generation/``, call the LLM,
    parse structured JSON, and apply post-processing (Phase 3.3–3.4).
    """

    @abstractmethod
    async def generate(self, request: SQLGenerationRequest) -> SQLGenerationResult:
        """
        Produce SQL and metadata for the given request.

        Raises:
            LLMProviderError: Provider returned an error response.
            LLMProviderUnavailableError: Network or rate-limit failure.
            SQLGenerationError: Unparseable or invalid model output.
            PromptNotFoundError: Required prompt templates are missing.
        """
