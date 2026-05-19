"""Shared TestClient factory for Phase 7 product E2E tests."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import (
    LLMProviderKind,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from insightai.infrastructure.ai.answer_generator import LLMAnswerGenerator
from insightai.infrastructure.ai.factory import AIComponents
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.database.bootstrap import (
    DatabaseComponents,
    build_database_components,
)
from insightai.infrastructure.prompts.loader import (
    load_answer_generation_prompts,
    load_answer_generation_stream_prompts,
    load_sql_generation_prompts,
)
from tests.conftest import make_settings
from tests.fixtures.answer_generation_samples import CLASSROOM_ANSWER_LLM_JSON
from tests.fixtures.sqlite_e2e_schema import CLASSROOM_SQLITE_LLM_JSON, seed_classroom_sqlite

SQLITE_MEMORY_URL = "sqlite:///:memory:"


def _mock_llm_framework() -> MagicMock:
    sql_response = LLMResponse(
        content=CLASSROOM_SQLITE_LLM_JSON,
        model="test-sql",
        provider=LLMProviderKind.GROQ,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        finish_reason="stop",
    )
    answer_response = LLMResponse(
        content=CLASSROOM_ANSWER_LLM_JSON,
        model="test-answer",
        provider=LLMProviderKind.GROQ,
        usage=TokenUsage(prompt_tokens=15, completion_tokens=25, total_tokens=40),
        finish_reason="stop",
    )

    async def _complete(request: LLMRequest, **_kwargs: object) -> LLMResponse:
        task = (request.metadata or {}).get("task", "")
        if task.startswith("answer_generation"):
            return answer_response
        return sql_response

    async def _complete_stream(request: LLMRequest, **_kwargs: object):
        task = (request.metadata or {}).get("task")
        if task == "answer_generation_stream":
            yield LLMStreamChunk(text="There are 2 classrooms in the result.")
            yield LLMStreamChunk(
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=15, completion_tokens=25, total_tokens=40),
            )
            return
        response = await _complete(request)
        if response.content:
            yield LLMStreamChunk(text=response.content)
        yield LLMStreamChunk(
            finish_reason=response.finish_reason,
            usage=response.usage if response.usage.has_usage else None,
        )

    provider = MagicMock()
    provider.provider_kind = LLMProviderKind.GROQ
    provider.default_model = "test-answer"

    framework = MagicMock()
    framework.complete = AsyncMock(side_effect=_complete)
    framework.complete_stream = _complete_stream
    framework.get_llm_provider = MagicMock(return_value=provider)
    return framework


def build_product_chat_client(
    **settings_overrides: Any,
) -> tuple[TestClient, DatabaseComponents, ExitStack]:
    """Create a TestClient with SQLite DB and mocked LLM (SQL + answer)."""
    settings_kwargs: dict[str, Any] = {
        "groq_api_key": "gsk-product-e2e",
        "database_kind": DatabaseKind.SQLITE,
        "database_readonly_url": SQLITE_MEMORY_URL,
        "rate_limit_enabled": False,
    }
    settings_kwargs.update(settings_overrides)
    settings = make_settings(**settings_kwargs)
    components = build_database_components(settings)
    seed_classroom_sqlite(components.engine)

    framework = _mock_llm_framework()
    sql_generator = LLMSQLGenerator(
        framework,
        settings,
        prompt_bundle=load_sql_generation_prompts(settings),
        sql_validator=components.validator,
    )
    answer_generator = LLMAnswerGenerator(
        framework,
        settings,
        prompt_bundle=load_answer_generation_prompts(settings),
        stream_prompt_bundle=load_answer_generation_stream_prompts(settings),
    )
    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=framework,
        sql_generator=sql_generator,
        answer_generator=answer_generator,
    )

    from insightai.main import create_app

    stack = ExitStack()
    stack.enter_context(patch("insightai.main.get_settings", return_value=settings))
    stack.enter_context(patch("insightai.main.build_ai_components", return_value=ai))
    stack.enter_context(
        patch("insightai.main.build_database_components", return_value=components),
    )

    app = create_app()
    client = TestClient(app)
    client.__enter__()
    stack.callback(client.__exit__, None, None, None)
    return client, components, stack


def dispose_product_client(
    components: DatabaseComponents,
    stack: ExitStack | None = None,
) -> None:
    if stack is not None:
        stack.close()
    components.engine.dispose()


@pytest.fixture
def product_chat_client() -> Generator[TestClient, None, None]:
    """Product API client: SQLite + mocked LLM, auth/rate-limit off."""
    client, components, stack = build_product_chat_client()
    try:
        yield client
    finally:
        dispose_product_client(components, stack)


@pytest.fixture
def product_chat_client_auth() -> Generator[tuple[TestClient, str], None, None]:
    """Product client with API key auth enabled."""
    api_key = "e2e-product-api-key"
    client, components, stack = build_product_chat_client(
        api_auth_mode="api_key",
        api_keys=api_key,
    )
    try:
        yield client, api_key
    finally:
        dispose_product_client(components, stack)
