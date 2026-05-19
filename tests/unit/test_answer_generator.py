"""Unit tests for LLMAnswerGenerator (mocked framework)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.domain.exceptions import AnswerGenerationParseError, LLMProviderError
from insightai.domain.models.answer import AnswerGenerationRequest
from insightai.domain.models.database import QueryColumn, QueryResult
from insightai.domain.models.llm import (
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
    join_stream_text,
)
from insightai.infrastructure.ai.answer_generator import LLMAnswerGenerator
from insightai.infrastructure.prompts.loader import (
    load_answer_generation_prompts,
    load_answer_generation_stream_prompts,
)
from tests.conftest import make_settings

_LLM_JSON = json.dumps(
    {
        "answer": "Room A has 2 children and Room B has 1.",
        "summary_bullets": ["classroom_id 10 → 2 children"],
        "row_count_cited": 2,
        "truncation_noted": False,
        "caveats": "",
    }
)


@pytest.fixture
def prompt_bundle():
    return load_answer_generation_prompts()


@pytest.fixture
def sample_result() -> QueryResult:
    return QueryResult(
        columns=[
            QueryColumn(name="classroom_id"),
            QueryColumn(name="child_count"),
        ],
        rows=[
            {"classroom_id": 10, "child_count": 2},
            {"classroom_id": 20, "child_count": 1},
        ],
        row_count=2,
        truncated=False,
        execution_time_ms=5.0,
        executed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_generate_uses_settings_answer_max_prompt_rows(
    prompt_bundle,
    sample_result,
) -> None:
    settings = make_settings(groq_api_key="gsk-test", answer_max_prompt_rows=3)
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=_LLM_JSON,
            model="test",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(),
            finish_reason="stop",
        ),
    )
    generator = LLMAnswerGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)
    large_result = sample_result.model_copy(
        update={
            "rows": [{"classroom_id": i, "child_count": 1} for i in range(20)],
            "row_count": 20,
        },
    )
    await generator.generate(
        AnswerGenerationRequest(
            question="How many?",
            sql="SELECT 1",
            query_result=large_result,
        ),
    )
    user_content = mock_framework.complete.await_args.args[0].messages[1].content
    assert "Sampled 3 of 20" in user_content


@pytest.mark.asyncio
async def test_generate_returns_parsed_answer(prompt_bundle, sample_result) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=_LLM_JSON,
            model="llama-3.3-70b-versatile",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(prompt_tokens=80, completion_tokens=40, total_tokens=120),
            finish_reason="stop",
        )
    )
    generator = LLMAnswerGenerator(
        mock_framework,
        settings,
        prompt_bundle=prompt_bundle,
    )
    request = AnswerGenerationRequest(
        question="How many children per classroom?",
        sql="SELECT classroom_id, COUNT(*) AS child_count FROM enrollments GROUP BY classroom_id",
        query_result=sample_result,
    )
    result = await generator.generate(request)

    assert "Room A" in result.answer
    assert result.row_count == 2
    assert result.truncation_noted is False
    assert result.usage.total_tokens == 120
    assert result.provider == LLMProviderKind.GROQ

    call_args = mock_framework.complete.await_args
    assert call_args is not None
    llm_request: LLMRequest = call_args.args[0]
    assert llm_request.metadata == {"task": "answer_generation"}
    assert "How many children per classroom?" in llm_request.messages[1].content
    assert "classroom_id" in llm_request.messages[1].content


@pytest.mark.asyncio
async def test_generate_uses_authoritative_row_count_when_model_differs(
    prompt_bundle,
    sample_result,
) -> None:
    mismatched = json.dumps(
        {
            "answer": "Found rows.",
            "summary_bullets": [],
            "row_count_cited": 99,
            "truncation_noted": False,
            "caveats": "",
        }
    )
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=mismatched,
            model="test",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(),
            finish_reason="stop",
        )
    )
    generator = LLMAnswerGenerator(
        mock_framework,
        settings,
        prompt_bundle=prompt_bundle,
    )
    result = await generator.generate(
        AnswerGenerationRequest(
            question="Count?",
            sql="SELECT 1",
            query_result=sample_result,
        ),
    )
    assert result.row_count == 2


@pytest.mark.asyncio
async def test_generate_truncation_noted_from_query_result(prompt_bundle) -> None:
    truncated_result = QueryResult(
        columns=[QueryColumn(name="id")],
        rows=[{"id": 1}],
        row_count=1,
        truncated=True,
    )
    llm_json = json.dumps(
        {
            "answer": "One row shown.",
            "summary_bullets": [],
            "row_count_cited": 1,
            "truncation_noted": False,
            "caveats": "",
        }
    )
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=llm_json,
            model="test",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(),
            finish_reason="stop",
        )
    )
    generator = LLMAnswerGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)
    result = await generator.generate(
        AnswerGenerationRequest(
            question="List ids",
            sql="SELECT id FROM t",
            query_result=truncated_result,
        ),
    )
    assert result.truncation_noted is True


@pytest.mark.asyncio
async def test_generate_propagates_llm_errors(prompt_bundle, sample_result) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(side_effect=LLMProviderError("api error"))
    generator = LLMAnswerGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)

    with pytest.raises(LLMProviderError):
        await generator.generate(
            AnswerGenerationRequest(
                question="Q",
                sql="SELECT 1",
                query_result=sample_result,
            ),
        )


@pytest.mark.asyncio
async def test_generate_stream_yields_tokens_and_done(sample_result) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    stream_bundle = load_answer_generation_stream_prompts()
    mock_framework = MagicMock()

    async def mock_stream(request: LLMRequest):
        yield LLMStreamChunk(text="There are ")
        yield LLMStreamChunk(text="2 classrooms.")
        yield LLMStreamChunk(finish_reason="stop", usage=TokenUsage(total_tokens=10))

    mock_framework.complete_stream = mock_stream
    mock_provider = MagicMock()
    mock_provider.provider_kind = LLMProviderKind.GROQ
    mock_provider.default_model = "llama-test"
    mock_framework.get_llm_provider = MagicMock(return_value=mock_provider)

    generator = LLMAnswerGenerator(
        mock_framework,
        settings,
        stream_prompt_bundle=stream_bundle,
    )
    request = AnswerGenerationRequest(
        question="How many classrooms?",
        sql="SELECT COUNT(*) FROM classrooms",
        query_result=sample_result,
    )

    events = [event async for event in generator.generate_stream(request)]
    assert [e.kind for e in events] == ["token", "token", "done"]
    assert (
        join_stream_text([LLMStreamChunk(text=e.text_delta) for e in events if e.text_delta])
        == "There are 2 classrooms."
    )
    assert events[-1].result is not None
    assert events[-1].result.answer == "There are 2 classrooms."
    assert events[-1].result.row_count == 2
    assert events[-1].result.summary_bullets == []


@pytest.mark.asyncio
async def test_generate_stream_uses_stream_system_prompt(sample_result) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    stream_bundle = load_answer_generation_stream_prompts()
    captured: list[LLMRequest] = []

    async def mock_stream(request: LLMRequest):
        captured.append(request)
        yield LLMStreamChunk(text="Done.")
        yield LLMStreamChunk(finish_reason="stop")

    mock_framework = MagicMock()
    mock_framework.complete_stream = mock_stream
    mock_framework.get_llm_provider = MagicMock(
        return_value=MagicMock(
            provider_kind=LLMProviderKind.GROQ,
            default_model="llama-test",
        ),
    )
    generator = LLMAnswerGenerator(
        mock_framework,
        settings,
        stream_prompt_bundle=stream_bundle,
    )
    await anext(
        generator.generate_stream(
            AnswerGenerationRequest(
                question="Q?",
                sql="SELECT 1",
                query_result=sample_result,
            )
        )
    )
    assert captured[0].metadata == {"task": "answer_generation_stream"}
    assert "plain natural language" in captured[0].messages[0].content.lower()


@pytest.mark.asyncio
async def test_generate_invalid_json_raises(prompt_bundle, sample_result) -> None:
    settings = make_settings(groq_api_key="gsk-test")
    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content="Sorry, I cannot format that.",
            model="test",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(),
            finish_reason="stop",
        ),
    )
    generator = LLMAnswerGenerator(mock_framework, settings, prompt_bundle=prompt_bundle)

    with pytest.raises(AnswerGenerationParseError):
        await generator.generate(
            AnswerGenerationRequest(
                question="Q",
                sql="SELECT 1",
                query_result=sample_result,
            ),
        )
