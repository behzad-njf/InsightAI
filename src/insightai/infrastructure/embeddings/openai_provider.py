"""OpenAI embedding provider (Phase 10.1)."""

from __future__ import annotations

from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from insightai.domain.exceptions import EmbeddingProviderError, EmbeddingProviderUnavailableError
from insightai.domain.models.embedding import (
    EmbeddingProviderKind,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)
from insightai.domain.ports.embedding_provider import IEmbeddingProvider  # noqa: TC001
from insightai.infrastructure.ai.providers.base import provider_error_message
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger

logger = get_logger(__name__)

_RETRYABLE = (APIConnectionError, RateLimitError, TimeoutError)


class OpenAIEmbeddingProvider(IEmbeddingProvider):
    """OpenAI ``/v1/embeddings`` via ``openai.AsyncOpenAI``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.require_openai_api_key(),
            timeout=settings.embedding_timeout_seconds,
            max_retries=0,
        )
        self._default_model = settings.embedding_model
        self._dimensions = settings.resolved_embedding_dimensions()

    @property
    def provider_kind(self) -> EmbeddingProviderKind:
        return EmbeddingProviderKind.OPENAI

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        if len(request.texts) > self._settings.embedding_max_batch_size:
            msg = (
                f"Embedding batch size {len(request.texts)} exceeds "
                f"INSIGHTAI_EMBEDDING_MAX_BATCH_SIZE={self._settings.embedding_max_batch_size}."
            )
            raise EmbeddingProviderError(msg)

        model = request.model or self._default_model
        try:
            response = await self._embed_with_retry(
                model=model,
                texts=request.texts,
            )
        except _RETRYABLE as exc:
            raise EmbeddingProviderUnavailableError(provider_error_message(exc)) from exc
        except APIStatusError as exc:
            raise EmbeddingProviderError(provider_error_message(exc)) from exc
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(provider_error_message(exc)) from exc

        return self._parse_response(response, model=model)

    async def _embed_with_retry(self, *, model: str, texts: list[str]) -> Any:
        kwargs: dict[str, Any] = {"model": model, "input": texts}
        if self._settings.embedding_dimensions is not None:
            kwargs["dimensions"] = self._settings.embedding_dimensions

        @retry(
            reraise=True,
            stop=stop_after_attempt(self._settings.embedding_max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        async def _call() -> Any:
            return await self._client.embeddings.create(**kwargs)

        return await _call()

    def _parse_response(self, response: Any, *, model: str) -> EmbeddingResult:
        data = sorted(response.data, key=lambda item: int(item.index))
        vectors = [
            EmbeddingVector(index=int(item.index), values=list(item.embedding))
            for item in data
        ]
        if not vectors:
            raise EmbeddingProviderError("OpenAI embeddings response contained no vectors.")

        dimensions = len(vectors[0].values)
        usage = EmbeddingUsage()
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            usage = EmbeddingUsage(
                prompt_tokens=getattr(raw_usage, "prompt_tokens", None),
                total_tokens=getattr(raw_usage, "total_tokens", None),
            )

        logger.info(
            "embedding_complete",
            provider="openai",
            model=model,
            count=len(vectors),
            dimensions=dimensions,
        )

        return EmbeddingResult(
            vectors=vectors,
            model=model,
            dimensions=dimensions,
            provider=EmbeddingProviderKind.OPENAI,
            usage=usage,
        )
