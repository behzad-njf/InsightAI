"""YAML-backed semantic catalog loader (Phase 11)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from insightai.domain.exceptions import SemanticConfigError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import (
    ExampleQuery,
    SemanticCatalog,
    TrustedMetric,
)
from insightai.domain.ports.semantic_catalog_loader import ISemanticCatalogLoader
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

_TRUSTED_METRICS_FILE = "trusted_metrics.yaml"
_EXAMPLE_QUERIES_FILE = "example_queries.yaml"


class YamlSemanticCatalogLoader(ISemanticCatalogLoader):
    """Load ``SemanticCatalog`` from ``config/semantic/`` (or a custom directory)."""

    def __init__(self, semantic_dir: Path) -> None:
        self._semantic_dir = semantic_dir.resolve()
        self._catalog: SemanticCatalog | None = None

    @property
    def semantic_dir(self) -> Path:
        return self._semantic_dir

    def load(self) -> SemanticCatalog:
        if self._catalog is not None:
            return self._catalog
        self._catalog = self._load_from_disk()
        return self._catalog

    def reload(self) -> SemanticCatalog:
        self._catalog = None
        return self.load()

    def _load_from_disk(self) -> SemanticCatalog:
        if not self._semantic_dir.is_dir():
            msg = f"Semantic config directory not found: {self._semantic_dir}"
            raise SemanticConfigError(msg)

        source_paths: list[str] = []
        metrics: list[TrustedMetric] = []
        examples: list[ExampleQuery] = []

        metrics_path = self._semantic_dir / _TRUSTED_METRICS_FILE
        if metrics_path.is_file():
            raw = _read_yaml(metrics_path)
            metrics = _parse_metrics(raw, source=str(metrics_path))
            source_paths.append(str(metrics_path))
        else:
            logger.warning(
                "semantic_metrics_file_missing",
                path=str(metrics_path),
                semantic_dir=str(self._semantic_dir),
            )

        examples_path = self._semantic_dir / _EXAMPLE_QUERIES_FILE
        if examples_path.is_file():
            raw = _read_yaml(examples_path)
            examples = _parse_example_queries(raw, source=str(examples_path))
            source_paths.append(str(examples_path))
        else:
            logger.warning(
                "semantic_examples_file_missing",
                path=str(examples_path),
                semantic_dir=str(self._semantic_dir),
            )

        catalog = SemanticCatalog(
            metrics=metrics,
            example_queries=examples,
            source_paths=source_paths,
        )
        logger.info(
            "semantic_catalog_loaded",
            semantic_dir=str(self._semantic_dir),
            metric_count=len(metrics),
            example_query_count=len(examples),
        )
        return catalog


def empty_semantic_catalog() -> SemanticCatalog:
    """Catalog with no assets (used when semantic layer is disabled)."""
    return SemanticCatalog()


def _read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Cannot read semantic config file: {path}"
        raise SemanticConfigError(msg) from exc
    if not text.strip():
        return {}
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in {path}: {exc}"
        raise SemanticConfigError(msg) from exc


def _parse_metrics(raw: Any, *, source: str) -> list[TrustedMetric]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        msg = f"{source}: root must be a mapping with key 'metrics'"
        raise SemanticConfigError(msg)
    items = raw.get("metrics", [])
    if items is None:
        return []
    if not isinstance(items, list):
        msg = f"{source}: 'metrics' must be a list"
        raise SemanticConfigError(msg)

    metrics: list[TrustedMetric] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            msg = f"{source}: metrics[{index}] must be a mapping"
            raise SemanticConfigError(msg)
        metric = _parse_metric_item(item, source=source, index=index)
        if metric.id in seen_ids:
            msg = f"{source}: duplicate metric id {metric.id!r}"
            raise SemanticConfigError(msg)
        seen_ids.add(metric.id)
        metrics.append(metric)
    return metrics


def _parse_example_queries(raw: Any, *, source: str) -> list[ExampleQuery]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        msg = f"{source}: root must be a mapping with key 'example_queries'"
        raise SemanticConfigError(msg)
    items = raw.get("example_queries", [])
    if items is None:
        return []
    if not isinstance(items, list):
        msg = f"{source}: 'example_queries' must be a list"
        raise SemanticConfigError(msg)

    examples: list[ExampleQuery] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            msg = f"{source}: example_queries[{index}] must be a mapping"
            raise SemanticConfigError(msg)
        example = _parse_example_item(item, source=source, index=index)
        if example.id in seen_ids:
            msg = f"{source}: duplicate example_queries id {example.id!r}"
            raise SemanticConfigError(msg)
        seen_ids.add(example.id)
        examples.append(example)
    return examples


def _parse_metric_item(item: dict[str, Any], *, source: str, index: int) -> TrustedMetric:
    prefix = f"{source}: metrics[{index}]"
    metric_id = _require_str(item, "id", prefix=prefix)
    title = _require_str(item, "title", prefix=prefix)
    sql = _require_str(item, "sql", prefix=prefix)
    try:
        return TrustedMetric(
            id=metric_id,
            title=title,
            sql=sql,
            description=_optional_str(item.get("description"), default=""),
            question_hints=_optional_str_list(item.get("question_hints")),
            tags=_optional_str_list(item.get("tags")),
            enabled=_optional_bool(item.get("enabled"), default=True),
            dialect=_optional_dialect(item.get("dialect"), prefix=prefix),
        )
    except ValueError as exc:
        msg = f"{prefix}: {exc}"
        raise SemanticConfigError(msg) from exc


def _parse_example_item(item: dict[str, Any], *, source: str, index: int) -> ExampleQuery:
    prefix = f"{source}: example_queries[{index}]"
    example_id = _require_str(item, "id", prefix=prefix)
    question = _require_str(item, "question", prefix=prefix)
    sql = _require_str(item, "sql", prefix=prefix)
    try:
        return ExampleQuery(
            id=example_id,
            question=question,
            sql=sql,
            description=_optional_str(item.get("description"), default=""),
            question_aliases=_optional_str_list(item.get("question_aliases")),
            tags=_optional_str_list(item.get("tags")),
            enabled=_optional_bool(item.get("enabled"), default=True),
            dialect=_optional_dialect(item.get("dialect"), prefix=prefix),
        )
    except ValueError as exc:
        msg = f"{prefix}: {exc}"
        raise SemanticConfigError(msg) from exc


def _require_str(data: dict[str, Any], key: str, *, prefix: str) -> str:
    if key not in data:
        msg = f"{prefix}: missing required field '{key}'"
        raise SemanticConfigError(msg)
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        msg = f"{prefix}: '{key}' must be a non-empty string"
        raise SemanticConfigError(msg)
    return value.strip()


def _optional_str(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        msg = "expected string"
        raise ValueError(msg)
    return value.strip()


def _optional_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        msg = "expected list of strings"
        raise ValueError(msg)
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            msg = "list entries must be non-empty strings"
            raise ValueError(msg)
        result.append(entry.strip())
    return result


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        msg = "expected boolean"
        raise ValueError(msg)
    return value


def _optional_dialect(value: Any, *, prefix: str) -> DatabaseKind | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{prefix}: 'dialect' must be a string"
        raise SemanticConfigError(msg)
    normalized = value.strip().lower()
    aliases = {
        "postgres": DatabaseKind.POSTGRESQL,
        "pg": DatabaseKind.POSTGRESQL,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return DatabaseKind(normalized)
    except ValueError as exc:
        allowed = ", ".join(k.value for k in DatabaseKind)
        msg = f"{prefix}: invalid dialect {value!r}; use one of: {allowed}"
        raise SemanticConfigError(msg) from exc
