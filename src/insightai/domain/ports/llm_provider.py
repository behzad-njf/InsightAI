"""LLM provider port — implemented by Groq, OpenAI, and future adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from insightai.domain.models.llm import (
        LLMProviderKind,
        LLMRequest,
        LLMResponse,
        LLMStreamChunk,
    )


class ILLMProvider(ABC):
    """
    Unified interface for chat completion providers.

    Infrastructure implementations must not leak SDK types beyond adapters.
    """

    @property
    @abstractmethod
    def provider_kind(self) -> LLMProviderKind:
        """Provider identifier (groq, openai, ...)."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model name from configuration."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Run a chat completion.

        Raises:
            LLMProviderError: Provider returned an error response.
            LLMProviderUnavailableError: Network or rate-limit failure after retries.
        """

    async def complete_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Stream completion chunks from the provider.

        Default: one-shot via ``complete()`` (providers override for true streaming).

        Raises:
            LLMProviderError: Provider returned an error response.
            LLMProviderUnavailableError: Network or rate-limit failure after retries.
        """
        from insightai.domain.models.llm import LLMStreamChunk

        response = await self.complete(request)
        if response.content:
            yield LLMStreamChunk(text=response.content)
        yield LLMStreamChunk(
            finish_reason=response.finish_reason,
            usage=response.usage if response.usage.has_usage else None,
        )

    async def health_check(self) -> bool:
        """
        Optional lightweight check that credentials and API are reachable.

        Default: True (override in adapters for real ping).
        """
        return True
