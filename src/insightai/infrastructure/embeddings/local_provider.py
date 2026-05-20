"""Deterministic local embeddings for development and tests (Phase 10.1)."""

from __future__ import annotations

import hashlib
import math
import struct

from insightai.domain.models.embedding import (
    EmbeddingProviderKind,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingVector,
)
from insightai.domain.ports.embedding_provider import IEmbeddingProvider


class LocalEmbeddingProvider(IEmbeddingProvider):
    """
    Hash-derived pseudo-embeddings (no external API).

    Vectors are L2-normalized and deterministic for the same input text.
    Suitable for unit tests and offline dev; not semantically meaningful.
    """

    def __init__(self, *, model: str, dimensions: int) -> None:
        if dimensions < 8:
            msg = "Local embedding dimensions must be at least 8."
            raise ValueError(msg)
        self._model = model
        self._dimensions = dimensions

    @property
    def provider_kind(self) -> EmbeddingProviderKind:
        return EmbeddingProviderKind.LOCAL

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        model = request.model or self._model
        vectors = [
            EmbeddingVector(index=index, values=self._vectorize(text))
            for index, text in enumerate(request.texts)
        ]
        return EmbeddingResult(
            vectors=vectors,
            model=model,
            dimensions=self._dimensions,
            provider=EmbeddingProviderKind.LOCAL,
        )

    def _vectorize(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode()).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self._dimensions:
            if counter == 0:
                block = seed
            else:
                block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            counter += 1
            for offset in range(0, len(block), 4):
                if len(values) >= self._dimensions:
                    break
                chunk = block[offset : offset + 4]
                if len(chunk) < 4:
                    break
                raw = struct.unpack("!f", chunk)[0]
                if math.isfinite(raw):
                    values.append(raw)
                else:
                    values.append(0.0)
        return _l2_normalize(values[: self._dimensions])


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0.0:
        return [0.0] * len(values)
    return [value / norm for value in values]
