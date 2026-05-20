"""LangChain optional dependency probe (Phase 10.5)."""

from __future__ import annotations


def langchain_available() -> bool:
    """True when LangChain agent packages are installed (``insightai[langchain]``)."""
    try:
        import langchain_openai  # noqa: F401
        from langchain.agents import create_agent  # noqa: F401
    except ImportError:
        return False
    return True
