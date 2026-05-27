"""Instantiate schema context builder (default or optional deployment plugin)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, cast

from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.schema.context_builder import SchemaContextBuilder
from insightai.infrastructure.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult


class ISchemaContextBuilder(Protocol):
    """Minimal interface for default and plugin builders."""

    def build(self, request: SchemaContextRequest) -> SchemaContextResult: ...


class _SchemaContextBuilderFactory(Protocol):
    def __call__(self, registry: SchemaRegistry) -> ISchemaContextBuilder: ...


def _load_plugin_class(dotted_path: str) -> _SchemaContextBuilderFactory:
    """
    Load ``module.path:ClassName`` from ``INSIGHTAI_SCHEMA_CONTEXT_PLUGIN``.

    Example: ``context.plugins.schema_context_extended:ExtendedSchemaContextBuilder``
    """
    if ":" not in dotted_path:
        msg = (
            "INSIGHTAI_SCHEMA_CONTEXT_PLUGIN must be module.path:ClassName, "
            f"got {dotted_path!r}"
        )
        raise ValueError(msg)
    module_path, class_name = dotted_path.split(":", 1)
    module = importlib.import_module(module_path.strip())
    plugin_cls = getattr(module, class_name.strip())
    if not callable(plugin_cls):
        msg = f"Plugin class {class_name!r} is not callable"
        raise TypeError(msg)
    return cast("_SchemaContextBuilderFactory", plugin_cls)


def create_schema_context_builder(
    registry: SchemaRegistry,
    settings: Settings | None = None,
) -> ISchemaContextBuilder:
    """
    Return the schema context builder for this process.

    Default: schema-driven ``SchemaContextBuilder`` (tables, FKs, domains, examples).
    Optional: deployment plugin under ``context/plugins/`` when configured.
    """
    settings = settings or get_settings()
    plugin_path = (settings.schema_context_plugin or "").strip()
    if plugin_path:
        plugin_cls = _load_plugin_class(plugin_path)
        return plugin_cls(registry)
    return SchemaContextBuilder(registry)
