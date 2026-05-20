"""LangChain agent path tests (Phase 10.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from insightai.application.use_cases.langchain_agent_ask import LangChainAgentAskUseCase
from insightai.domain.models.ask import AskRequest
from insightai.domain.models.hybrid import QueryRouteKind, RAGRetrievalResult, RAGSourceCitation
from insightai.domain.models.langchain_agent import LangChainAgentRunResult
from insightai.infrastructure.ai.frameworks.langchain_adapter import LangChainFrameworkAdapter
from insightai.infrastructure.ai.langchain.availability import langchain_available
from tests.conftest import make_settings
from tests.unit.test_ask_use_case import _answer_result, _run_result, _sql_result


@pytest.mark.asyncio
async def test_langchain_adapter_delegates_complete() -> None:
    settings = make_settings(groq_api_key="gsk-test")
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_provider.complete = AsyncMock(return_value=mock_response)
    mock_provider.provider_kind = MagicMock(value="groq")

    framework = LangChainFrameworkAdapter(mock_provider, settings)
    from insightai.domain.models.llm import LLMMessage, LLMRequest, LLMRole

    request = LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="Hi")])
    result = await framework.complete(request)
    assert result is mock_response
    mock_provider.complete.assert_awaited_once()


def test_langchain_available_without_packages() -> None:
    with patch(
        "insightai.infrastructure.ai.factory.langchain_available",
        return_value=False,
    ):
        from insightai.domain.exceptions import LLMConfigurationError
        from insightai.domain.models.llm import AIFrameworkKind
        from insightai.infrastructure.ai.factory import create_ai_framework

        settings = make_settings(
            ai_framework=AIFrameworkKind.LANGCHAIN,
            groq_api_key="gsk-test",
        )
        with pytest.raises(LLMConfigurationError, match="langchain"):
            create_ai_framework(settings=settings)


@pytest.mark.asyncio
async def test_langchain_agent_ask_maps_agent_result() -> None:
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(
        return_value=LangChainAgentRunResult(
            question="How many classrooms?",
            answer="There are 12 classrooms.",
            tools_used=["run_sql_analytics"],
            sql=_sql_result(),
            execution=_run_result(),
            agent_ms=50.0,
        ),
    )
    generate_answer = MagicMock()
    generate_answer.execute = AsyncMock(return_value=_answer_result())

    use_case = LangChainAgentAskUseCase(
        agent_runner,
        generate_answer,
        settings=make_settings(rag_enabled=True, langchain_agent_enabled=True),
        audit=MagicMock(),
    )
    result = await use_case.execute(AskRequest(question="How many classrooms?"))

    assert result.route == QueryRouteKind.AGENT
    assert result.sql is not None
    assert result.execution is not None
    generate_answer.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_langchain_agent_ask_rag_only_uses_agent_text() -> None:
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(
        return_value=LangChainAgentRunResult(
            question="What is late pickup policy?",
            answer="Notify the front desk [1].",
            tools_used=["search_documents"],
            rag_retrieval=RAGRetrievalResult(
                question="What is late pickup policy?",
                sources=[
                    RAGSourceCitation(
                        id="c1",
                        source_path="policy.md",
                        chunk_index=0,
                        text="Notify the front desk.",
                        score=0.9,
                    ),
                ],
                top_k=5,
            ),
            agent_ms=30.0,
        ),
    )
    generate_answer = MagicMock()

    use_case = LangChainAgentAskUseCase(
        agent_runner,
        generate_answer,
        settings=make_settings(),
        audit=MagicMock(),
    )
    result = await use_case.execute(AskRequest(question="What is late pickup policy?"))

    assert result.route == QueryRouteKind.AGENT
    assert "front desk" in result.answer.answer.answer
    generate_answer.execute.assert_not_called()


@pytest.mark.skipif(not langchain_available(), reason="insightai[langchain] not installed")
def test_langchain_tools_build() -> None:
    from insightai.infrastructure.ai.langchain.tool_context import LangChainAgentToolContext
    from insightai.infrastructure.ai.langchain.tools import build_langchain_tools

    context = LangChainAgentToolContext()
    tools = build_langchain_tools(
        retrieve_rag=MagicMock(),
        generate_sql=MagicMock(),
        run_query=MagicMock(),
        settings=make_settings(),
        context=context,
    )
    names = {tool.__name__ for tool in tools}
    assert names == {"search_documents", "run_sql_analytics"}
