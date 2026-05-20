"""LangChain agent integration (Phase 10.5)."""

from insightai.infrastructure.ai.langchain.agent_runner import LangChainAgentRunner
from insightai.infrastructure.ai.langchain.availability import langchain_available

__all__ = ["LangChainAgentRunner", "langchain_available"]
