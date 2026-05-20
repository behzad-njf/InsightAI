"""Unit tests for Phase 9.2 schema warm and context caching."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.domain.models.schema import SchemaContextRequest, SchemaContextResult
from insightai.infrastructure.cache.memory_cache import MemoryCache
from insightai.infrastructure.schema.bootstrap import build_schema_components
from insightai.infrastructure.schema.context_cache import schema_context_cache_key
from tests.conftest import make_settings


@pytest.fixture
def schema_path() -> Path:
    return Path("schema/database_schema.md")


@pytest.mark.asyncio
async def test_schema_context_cache_hit_skips_repository(schema_path: Path) -> None:
    settings = make_settings(cache_enabled=True, cache_schema_context_enabled=True)
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=300)

    schema_result = SchemaContextResult(
        question="children in classroom",
        tables=[],
        join_patterns=[],
        context_markdown="### school_classroomchild",
        table_names=["school_classroomchild"],
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = schema_result

    use_case = BuildSchemaContextUseCase(
        mock_repository,
        cache=cache,
        settings=settings,
        schema_path=schema_path,
    )
    request = SchemaContextRequest(question="children in classroom", max_tables=12)

    first = await use_case.execute(request)
    second = await use_case.execute(request)

    assert first.table_names == second.table_names
    mock_repository.build_context.assert_called_once()


@pytest.mark.asyncio
async def test_schema_context_cache_keys_differ_by_user_scope(schema_path: Path) -> None:
    settings = make_settings(
        cache_enabled=True,
        cache_schema_context_enabled=True,
        cache_schema_context_scope_user=True,
    )
    cache = MemoryCache(key_prefix="test:", default_ttl_seconds=300)
    mock_repository = MagicMock()
    mock_repository.build_context.side_effect = lambda req: SchemaContextResult(
        question=req.question,
        tables=[],
        join_patterns=[],
        context_markdown="ctx",
        table_names=[req.question],
    )

    use_case = BuildSchemaContextUseCase(
        mock_repository,
        cache=cache,
        settings=settings,
        schema_path=schema_path,
    )
    request = SchemaContextRequest(question="same question", max_tables=12)

    await use_case.execute(request, cache_scope="user-a")
    await use_case.execute(request, cache_scope="user-b")

    assert mock_repository.build_context.call_count == 2


def test_build_schema_components_warms_registry() -> None:
    settings = make_settings()
    components = build_schema_components(settings)
    assert components.table_count > 0
    assert components.repository.get_document().table_count == components.table_count


def test_schema_context_cache_key_changes_with_mtime(schema_path: Path, tmp_path: Path) -> None:
    request = SchemaContextRequest(question="How many users?", max_tables=8)
    key_a = schema_context_cache_key(request, schema_path)
    other = tmp_path / "other_schema.md"
    other.write_text("# other", encoding="utf-8")
    key_b = schema_context_cache_key(request, other)
    assert key_a != key_b
