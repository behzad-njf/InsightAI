"""Unit tests for answer generation JSON parsing."""

from __future__ import annotations

import json

import pytest

from insightai.domain.exceptions import AnswerGenerationParseError
from insightai.domain.models.answer import AnswerGenerationLLMOutput
from insightai.infrastructure.ai.answer_response_parser import parse_answer_generation_llm_output

_VALID = json.dumps(
    {
        "answer": "The query returned 2 classrooms.",
        "summary_bullets": ["Room A has 2 children."],
        "row_count_cited": 2,
        "truncation_noted": False,
        "caveats": "",
    }
)


def test_parse_valid_json() -> None:
    output = parse_answer_generation_llm_output(_VALID)
    assert output.answer.startswith("The query returned")
    assert output.row_count_cited == 2
    assert output.summary_bullets == ["Room A has 2 children."]


def test_parse_json_in_fence() -> None:
    wrapped = f"```json\n{_VALID}\n```"
    output = parse_answer_generation_llm_output(wrapped)
    assert isinstance(output, AnswerGenerationLLMOutput)


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(AnswerGenerationParseError):
        parse_answer_generation_llm_output("not json at all")


def test_parse_double_braced_json_from_prompt_echo() -> None:
    """Models sometimes copy ``{{ ... }}`` from older prompt examples."""
    wrapped = "{" + _VALID + "}"
    output = parse_answer_generation_llm_output(wrapped)
    assert output.row_count_cited == 2


def test_parse_python_style_single_quoted_dict() -> None:
    content = """{'answer': 'You have 3 classrooms.', 'summary_bullets': [], """
    content += "'row_count_cited': 3, 'truncation_noted': False, 'caveats': ''}"
    output = parse_answer_generation_llm_output(content)
    assert "3 classrooms" in output.answer
