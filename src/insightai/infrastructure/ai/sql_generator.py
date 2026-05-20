"""LLM-backed SQL generator — prompts + framework completion (Phase 3.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.llm import LLMRequest
from insightai.domain.models.sql_generation import SQLGenerationRequest, SQLGenerationResult
from insightai.domain.ports.sql_generator import ISQLGenerator
from insightai.domain.ports.sql_safety import ISQLSafetyValidator
from insightai.infrastructure.ai.sql_postprocessor import postprocess_generated_sql
from insightai.infrastructure.ai.sql_response_parser import parse_sql_generation_llm_output
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.prompts.loader import (
    SQLGenerationPromptBundle,
    load_sql_generation_prompts,
    render_sql_generation_messages,
)
from insightai.infrastructure.ai.token_limits import cap_completion_tokens
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator

if TYPE_CHECKING:
    from insightai.domain.ports.ai_framework import IAIFramework

logger = get_logger(__name__)

# JSON + SQL responses need more tokens than short chat replies.
_DEFAULT_MAX_COMPLETION_TOKENS = 4096


class LLMSQLGenerator(ISQLGenerator):
    """
    Generates read-only SQL via configured prompts and ``IAIFramework.complete()``.

    Delegates to the underlying ``ILLMProvider`` (Groq/OpenAI) through the framework
    adapter; does not call LlamaIndex query engines directly in Phase 3.
    """

    def __init__(
        self,
        framework: IAIFramework,
        settings: Settings | None = None,
        *,
        prompt_bundle: SQLGenerationPromptBundle | None = None,
        max_completion_tokens: int = _DEFAULT_MAX_COMPLETION_TOKENS,
        sql_validator: ISQLSafetyValidator | None = None,
        enforce_readonly: bool = True,
    ) -> None:
        self._framework = framework
        self._settings = settings or get_settings()
        self._prompts = prompt_bundle or load_sql_generation_prompts(self._settings)
        self._max_completion_tokens = max_completion_tokens
        self._sql_validator = sql_validator or create_sql_safety_validator(
            settings=self._settings,
        )
        self._enforce_readonly = enforce_readonly

    async def generate(self, request: SQLGenerationRequest) -> SQLGenerationResult:
        messages = render_sql_generation_messages(
            question=request.question,
            schema_context=request.schema_context,
            database_kind=request.database_kind,
            max_rows=request.max_rows,
            settings=self._settings,
            bundle=self._prompts,
        )
        model = request.model or self._settings.get_active_llm_model()
        max_tokens = cap_completion_tokens(model, self._max_completion_tokens)

        llm_request = LLMRequest(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=max_tokens,
            metadata={"task": "sql_generation"},
        )

        logger.info(
            "sql_generation_start",
            dialect=request.database_kind.value,
            context_tables=len(request.schema_table_names),
            model=model,
            max_tokens=max_tokens,
        )
        llm_response = await self._framework.complete(llm_request)
        output = parse_sql_generation_llm_output(llm_response.content)
        processed_sql = output.sql
        if output.sql.strip():
            validator = create_sql_safety_validator(
                kind=request.database_kind,
                settings=self._settings,
            )
            postprocessed = postprocess_generated_sql(
                output.sql,
                validator=validator,
                database_kind=request.database_kind,
                settings=self._settings,
                enforce_readonly=self._enforce_readonly,
            )
            processed_sql = postprocessed.sql
        output = output.model_copy(update={"sql": processed_sql})

        result = SQLGenerationResult.from_llm_output(
            output,
            schema_table_names=request.schema_table_names,
            usage=llm_response.usage,
            model=llm_response.model,
            provider=llm_response.provider,
            finish_reason=llm_response.finish_reason,
        )
        logger.info(
            "sql_generation_complete",
            has_sql=result.has_sql,
            confidence=result.confidence.value,
            tables_used=len(result.tables_used),
        )
        return result
