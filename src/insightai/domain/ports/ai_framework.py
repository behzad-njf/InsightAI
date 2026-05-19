"""AI framework port — LlamaIndex primary; LangChain compatible later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.llm import (
        AIFrameworkKind,
        LLMRequest,
        LLMResponse,
        LLMStreamChunk,
    )
    from insightai.domain.ports.llm_provider import ILLMProvider


class IAIFramework(ABC):
    """
    Abstraction over LlamaIndex / LangChain for completions and future RAG.

    Application code depends on this port, not on framework SDKs.
    """

    @property
    @abstractmethod
    def framework_kind(self) -> AIFrameworkKind:
        """Framework identifier (llamaindex, langchain)."""

    @abstractmethod
    def get_llm_provider(self) -> ILLMProvider:
        """Return the underlying LLM provider used by this framework."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Framework-level completion (may add instrumentation, callbacks, RAG later).

        Phase 1: delegates to configured ILLMProvider.
        """

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Stream completion chunks (delegates to ``ILLMProvider.complete_stream``).

        Framework adapters may override to add instrumentation or RAG context later.
        """
        async for chunk in self.get_llm_provider().complete_stream(request):
            yield chunk
