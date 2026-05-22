"""Unit tests for Phase 11 YAML semantic catalog loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.exceptions import SemanticConfigError
from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.semantic.yaml_loader import (
    YamlSemanticCatalogLoader,
    empty_semantic_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SEMANTIC_DIR = PROJECT_ROOT / "tests" / "fixtures" / "semantic"
INSTANCE_SEMANTIC_DIR = PROJECT_ROOT / "config" / "semantic"


def test_load_fixture_catalog() -> None:
    loader = YamlSemanticCatalogLoader(FIXTURE_SEMANTIC_DIR)
    catalog = loader.load()
    assert len(catalog.metrics) == 1
    assert catalog.metrics[0].id == "fixture_active_user_count"
    assert catalog.metrics[0].dialect == DatabaseKind.MSSQL
    assert len(catalog.example_queries) == 1
    assert catalog.example_queries[0].id == "fixture_classroom_headcount"
    assert len(catalog.source_paths) == 2


def test_load_instance_empty_lists() -> None:
    loader = YamlSemanticCatalogLoader(INSTANCE_SEMANTIC_DIR)
    catalog = loader.load()
    assert catalog.metrics == []
    assert catalog.example_queries == []
    assert len(catalog.source_paths) == 2


def test_reload_refreshes_cache(tmp_path: Path) -> None:
    metrics_file = tmp_path / "trusted_metrics.yaml"
    metrics_file.write_text(
        "metrics:\n  - id: first\n    title: First\n    sql: SELECT 1\n",
        encoding="utf-8",
    )
    (tmp_path / "example_queries.yaml").write_text("example_queries: []\n", encoding="utf-8")

    loader = YamlSemanticCatalogLoader(tmp_path)
    assert loader.load().metrics[0].id == "first"

    metrics_file.write_text(
        "metrics:\n  - id: second\n    title: Second\n    sql: SELECT 2\n",
        encoding="utf-8",
    )
    assert loader.load().metrics[0].id == "first"
    reloaded = loader.reload()
    assert reloaded.metrics[0].id == "second"


def test_missing_semantic_dir_raises() -> None:
    loader = YamlSemanticCatalogLoader(PROJECT_ROOT / "nonexistent_semantic_dir")
    with pytest.raises(SemanticConfigError, match="not found"):
        loader.load()


def test_duplicate_metric_id_raises(tmp_path: Path) -> None:
    (tmp_path / "trusted_metrics.yaml").write_text(
        "metrics:\n"
        "  - id: dup\n    title: A\n    sql: SELECT 1\n"
        "  - id: dup\n    title: B\n    sql: SELECT 2\n",
        encoding="utf-8",
    )
    (tmp_path / "example_queries.yaml").write_text("example_queries: []\n", encoding="utf-8")
    loader = YamlSemanticCatalogLoader(tmp_path)
    with pytest.raises(SemanticConfigError, match="duplicate metric id"):
        loader.load()


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    (tmp_path / "trusted_metrics.yaml").write_text("metrics: [\n", encoding="utf-8")
    (tmp_path / "example_queries.yaml").write_text("example_queries: []\n", encoding="utf-8")
    loader = YamlSemanticCatalogLoader(tmp_path)
    with pytest.raises(SemanticConfigError, match="Invalid YAML"):
        loader.load()


def test_empty_semantic_catalog_helper() -> None:
    catalog = empty_semantic_catalog()
    assert catalog.metrics == []
    assert catalog.example_queries == []
    assert catalog.source_paths == []


def test_postgres_dialect_alias(tmp_path: Path) -> None:
    (tmp_path / "trusted_metrics.yaml").write_text(
        "metrics:\n  - id: pg_metric\n    title: PG\n    sql: SELECT 1\n    dialect: postgres\n",
        encoding="utf-8",
    )
    (tmp_path / "example_queries.yaml").write_text("example_queries: []\n", encoding="utf-8")
    catalog = YamlSemanticCatalogLoader(tmp_path).load()
    assert catalog.metrics[0].dialect == DatabaseKind.POSTGRESQL
