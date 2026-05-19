"""Parse structured JSON from LLM answer generation responses."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from insightai.domain.exceptions import AnswerGenerationParseError
from insightai.domain.models.answer import AnswerGenerationLLMOutput
from insightai.infrastructure.ai.sql_response_parser import (
    extract_json_text,
    loads_llm_json_object,
)


def parse_answer_generation_llm_output(content: str) -> AnswerGenerationLLMOutput:
    """Decode LLM content into ``AnswerGenerationLLMOutput``."""
    try:
        json_text = extract_json_text(content)
        data: Any = loads_llm_json_object(json_text)
        return AnswerGenerationLLMOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        msg = f"Failed to parse answer generation JSON: {exc}"
        raise AnswerGenerationParseError(msg) from exc
