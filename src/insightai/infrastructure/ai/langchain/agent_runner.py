"""LangChain tool-calling agent runner (Phase 10.5)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from insightai.domain.exceptions import AIFrameworkError, ConfigurationError
from insightai.domain.models.langchain_agent import LangChainAgentRunResult
from insightai.domain.models.llm import LLMProviderKind
from insightai.domain.ports.langchain_agent import ILangChainAgentRunner
from insightai.infrastructure.ai.langchain.availability import langchain_available
from insightai.infrastructure.ai.langchain.tool_context import LangChainAgentToolContext
from insightai.infrastructure.ai.langchain.tools import build_langchain_tools
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
    from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
    from insightai.application.use_cases.run_query import RunQueryUseCase

logger = get_logger(__name__)

_AGENT_SYSTEM_PROMPT = """You are InsightAI, a campus analytics assistant with two tools:

1. **search_documents** — policies, procedures, handbook text (semantic search).
2. **run_sql_analytics** — read-only SQL metrics (counts, trends, tables).

Choose the right tool(s). For hybrid questions, call both, then synthesize one clear answer.
Cite document sources as [1], [2] when using search results. Do not invent SQL results or policies.
When a tool returns no useful data, say so honestly."""


class LangChainAgentRunner(ILangChainAgentRunner):
    """LangChain 1.x ``create_agent`` graph over InsightAI RAG + SQL tools."""

    def __init__(
        self,
        retrieve_rag: RetrieveRAGContextUseCase,
        generate_sql: GenerateSQLUseCase,
        run_query: RunQueryUseCase,
        settings: Settings | None = None,
    ) -> None:
        if not langchain_available():
            msg = "LangChain is not installed. Install with: pip install 'insightai[langchain]'"
            raise ConfigurationError(msg)
        self._retrieve_rag = retrieve_rag
        self._generate_sql = generate_sql
        self._run_query = run_query
        self._settings = settings or get_settings()

    async def run(self, question: str) -> LangChainAgentRunResult:
        started = time.perf_counter()
        context = LangChainAgentToolContext()
        tools = build_langchain_tools(
            retrieve_rag=self._retrieve_rag,
            generate_sql=self._generate_sql,
            run_query=self._run_query,
            settings=self._settings,
            context=context,
        )

        try:
            answer_text = await self._invoke_agent(question.strip(), tools)
        except Exception as exc:
            msg = f"LangChain agent failed: {exc}"
            raise AIFrameworkError(msg) from exc

        agent_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "langchain_agent_complete",
            tools_used=context.tools_used,
            agent_ms=round(agent_ms, 2),
        )
        return LangChainAgentRunResult(
            question=question.strip(),
            answer=answer_text.strip(),
            tools_used=list(context.tools_used),
            rag_retrieval=context.rag_retrieval,
            sql=context.sql,
            execution=context.execution,
            agent_ms=round(agent_ms, 2),
        )

    async def _invoke_agent(self, question: str, tools: list[Any]) -> str:
        from langchain.agents import create_agent
        from langchain_core.messages import AIMessage

        llm = self._build_chat_model()
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=_AGENT_SYSTEM_PROMPT,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
        )
        messages = result.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = message.content
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):
                    parts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    joined = "".join(parts).strip()
                    if joined:
                        return joined
        msg = "LangChain agent returned no assistant message."
        raise AIFrameworkError(msg)

    def _build_chat_model(self) -> object:
        from langchain_openai import ChatOpenAI

        if self._settings.llm_provider == LLMProviderKind.GROQ:
            return ChatOpenAI(
                model=self._settings.groq_model,
                api_key=self._settings.require_groq_api_key(),
                base_url="https://api.groq.com/openai/v1",
                temperature=self._settings.llm_temperature,
                timeout=float(self._settings.groq_timeout_seconds),
            )
        if self._settings.llm_provider == LLMProviderKind.OPENAI:
            return ChatOpenAI(
                model=self._settings.openai_model,
                api_key=self._settings.require_openai_api_key(),
                temperature=self._settings.llm_temperature,
                timeout=float(self._settings.openai_timeout_seconds),
            )
        msg = f"LangChain agent does not support LLM provider: {self._settings.llm_provider}"
        raise ConfigurationError(msg)
