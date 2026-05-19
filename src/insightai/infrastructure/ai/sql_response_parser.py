"""Parse structured JSON from LLM SQL generation responses."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from pydantic import ValidationError

from insightai.domain.exceptions import SQLGenerationParseError
from insightai.domain.models.sql_generation import SQLGenerationLLMOutput

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json_text(content: str) -> str:
    """
    Pull a JSON object string from raw LLM content.

    Handles optional ```json fences and leading/trailing prose.
    """
    text = content.strip()
    if not text:
        msg = "LLM returned empty content."
        raise SQLGenerationParseError(msg)

    # Prefer raw JSON when the response starts with an object (sql field may contain ```sql).
    if text.startswith("{"):
        end = text.rfind("}")
        if end > 0:
            return text[: end + 1]
        return text

    if text.startswith("```"):
        fence_match = _JSON_FENCE_RE.search(text)
        if fence_match:
            return fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def unwrap_outer_double_braces(text: str) -> str:
    """
    Unwrap ``{{ ... }}`` when the model copies prompt examples literally.

    Answer generation system prompts must use single braces; SQL prompts use
    ``{{`` only because ``str.format`` runs on that template.
    """
    stripped = text.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        inner = stripped[1:-1].strip()
        if inner.startswith("{") and inner.endswith("}"):
            return inner
    return text


def loads_llm_json_object(json_text: str) -> Any:
    """Parse a JSON object string; tolerate Python-style dict literals as fallback."""
    normalized = unwrap_outer_double_braces(json_text)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(normalized)
        except (SyntaxError, ValueError) as exc:
            raise json.JSONDecodeError(str(exc), normalized, 0) from exc
        if not isinstance(value, dict):
            msg = "LLM JSON must decode to an object."
            raise json.JSONDecodeError(msg, normalized, 0)
        return value


def parse_sql_generation_llm_output(content: str) -> SQLGenerationLLMOutput:
    """Decode LLM content into ``SQLGenerationLLMOutput``."""
    try:
        json_text = extract_json_text(content)
        data: Any = loads_llm_json_object(json_text)
        return SQLGenerationLLMOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        msg = f"Failed to parse SQL generation JSON: {exc}"
        raise SQLGenerationParseError(msg) from exc
