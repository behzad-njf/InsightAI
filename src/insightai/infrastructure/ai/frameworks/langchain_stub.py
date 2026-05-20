"""Backward-compatible alias — use ``LangChainFrameworkAdapter`` (Phase 10.5)."""

from __future__ import annotations

from insightai.infrastructure.ai.frameworks.langchain_adapter import LangChainFrameworkAdapter

# Kept for imports in older tests/docs; adapter delegates LLM calls to ILLMProvider.
LangChainFrameworkStub = LangChainFrameworkAdapter

__all__ = ["LangChainFrameworkAdapter", "LangChainFrameworkStub"]
