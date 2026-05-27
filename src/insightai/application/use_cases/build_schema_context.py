"""Build schema context for SQL generation prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.infrastructure.observability.tracing import set_span_attributes, start_span
from insightai.infrastructure.schema.context_cache import (
    get_cached_schema_context,
    schema_context_cache_key,
    set_cached_schema_context,
)

if TYPE_CHECKING:
    from pathlib import Path

    from insightai.domain.ports.cache import ICache
    from insightai.domain.ports.schema_repository import ISchemaRepository
    from insightai.infrastructure.config.settings import Settings


class BuildSchemaContextUseCase:
    """Retrieve relevant schema metadata for a user question."""

    def __init__(
        self,
        schema_repository: ISchemaRepository,
        *,
        cache: ICache | None = None,
        settings: Settings | None = None,
        schema_path: Path | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._repository = schema_repository
        self._settings = settings or get_settings()
        self._cache = cache
        from insightai.infrastructure.schema.schema_loader import resolve_schema_cache_path

        self._schema_path = schema_path or resolve_schema_cache_path(self._settings)

    async def execute(
        self,
        request: SchemaContextRequest,
        *,
        cache_scope: str | None = None,
    ) -> SchemaContextResult:
        cache_active = self._schema_context_cache_active()
        key: str | None = None
        if cache_active and self._cache is not None:
            scope = self._resolve_cache_scope(cache_scope)
            key = schema_context_cache_key(
                request,
                self._schema_path,
                cache_scope=scope,
            )
            cached = await get_cached_schema_context(self._cache, key)
            if cached is not None:
                with start_span(
                    "insightai.schema.context",
                    attributes={
                        "insightai.schema.max_tables": request.max_tables,
                        "insightai.schema.cache_hit": True,
                    },
                ):
                    set_span_attributes(
                        {"insightai.schema.table_count": len(cached.table_names)},
                    )
                return cached

        with start_span(
            "insightai.schema.context",
            attributes={
                "insightai.schema.max_tables": request.max_tables,
                "insightai.schema.cache_hit": False,
            },
        ):
            result = self._repository.build_context(request)
            set_span_attributes(
                {"insightai.schema.table_count": len(result.table_names)},
            )

        if cache_active and self._cache is not None and key is not None:
            ttl = self._settings.cache_schema_context_ttl_seconds
            if ttl is None:
                ttl = self._settings.cache_default_ttl_seconds
            await set_cached_schema_context(
                self._cache,
                key,
                result,
                ttl_seconds=ttl,
            )

        return result

    def _schema_context_cache_active(self) -> bool:
        return self._settings.cache_enabled and self._settings.cache_schema_context_enabled

    def _resolve_cache_scope(self, cache_scope: str | None) -> str | None:
        if not self._settings.cache_schema_context_scope_user:
            return None
        return cache_scope
