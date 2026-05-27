"""Unit tests for trusted semantic wiring in GenerateSQLUseCase (Phase 11.5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.application.use_cases.match_trusted_sql import MatchTrustedSQLUseCase
from insightai.domain.models.schema import SchemaContextResult
from insightai.domain.models.semantic import GenerationSource
from insightai.domain.models.sql_generation import (
    GenerateSQLRequest,
    SQLGenerationConfidence,
    SQLGenerationRequest,
    SQLGenerationResult,
)
from insightai.infrastructure.semantic.trusted_matcher import TrustedSQLMatcher
from insightai.infrastructure.semantic.yaml_loader import YamlSemanticCatalogLoader
from tests.conftest import make_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SEMANTIC_DIR = PROJECT_ROOT / "tests" / "fixtures" / "semantic"


def _schema_context_result() -> SchemaContextResult:
    return SchemaContextResult(
        question="q",
        tables=[],
        join_patterns=[],
        context_markdown="### accounts_user",
        table_names=["accounts_user"],
    )


@pytest.mark.asyncio
async def test_trusted_question_match_skips_llm_when_use_llm_false() -> None:
    settings = make_settings(
        groq_api_key="gsk-test",
        semantic_enabled=True,
        semantic_path=FIXTURE_SEMANTIC_DIR,
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = _schema_context_result()

    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock()

    loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
    match_use_case = MatchTrustedSQLUseCase(loader, TrustedSQLMatcher(), settings=settings)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
        match_trusted=match_use_case,
    )

    result = await use_case.execute(
        GenerateSQLRequest(
            question="How many kids are in the Example classroom?",
            use_llm=False,
        ),
    )

    mock_generator.generate.assert_not_awaited()
    assert result.sql.generation_source == GenerationSource.TRUSTED_EXAMPLE
    assert result.sql.trusted_asset_id == "fixture_classroom_headcount"
    assert result.sql.has_sql is True


@pytest.mark.asyncio
async def test_no_trusted_match_calls_llm() -> None:
    settings = make_settings(
        groq_api_key="gsk-test",
        semantic_enabled=True,
        semantic_path=FIXTURE_SEMANTIC_DIR,
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = _schema_context_result()

    llm_result = SQLGenerationResult(
        sql="SELECT 1",
        explanation="fallback",
        confidence=SQLGenerationConfidence.HIGH,
        generation_source=GenerationSource.LLM,
    )
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=llm_result)

    loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
    match_use_case = MatchTrustedSQLUseCase(loader, TrustedSQLMatcher(), settings=settings)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
        match_trusted=match_use_case,
    )

    result = await use_case.execute(
        GenerateSQLRequest(question="completely unrelated question xyz"),
    )

    mock_generator.generate.assert_awaited_once()
    assert result.sql.generation_source == GenerationSource.LLM


@pytest.mark.asyncio
async def test_llm_sql_normalized_match_marks_trusted() -> None:
    settings = make_settings(
        groq_api_key="gsk-test",
        semantic_enabled=True,
        semantic_path=FIXTURE_SEMANTIC_DIR,
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = _schema_context_result()

    fixture_sql = (
        "SELECT COUNT(*) AS active_user_count "
        "FROM dbo.accounts_user AS u WHERE u.is_active = 1"
    )
    llm_result = SQLGenerationResult(
        sql=fixture_sql,
        explanation="LLM wrote the same SQL",
        confidence=SQLGenerationConfidence.HIGH,
    )
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=llm_result)

    loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
    match_use_case = MatchTrustedSQLUseCase(loader, TrustedSQLMatcher(), settings=settings)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
        match_trusted=match_use_case,
    )

    result = await use_case.execute(
        GenerateSQLRequest(question="unrelated", use_llm=True),
    )

    mock_generator.generate.assert_awaited_once()
    assert result.sql.generation_source == GenerationSource.TRUSTED_METRIC
    assert result.sql.trusted_asset_id == "fixture_active_user_count"


@pytest.mark.asyncio
async def test_use_llm_true_uses_llm_despite_question_match() -> None:
    settings = make_settings(
        groq_api_key="gsk-test",
        semantic_enabled=True,
        semantic_path=FIXTURE_SEMANTIC_DIR,
    )
    mock_repository = MagicMock()
    mock_repository.build_context.return_value = _schema_context_result()

    llm_result = SQLGenerationResult(
        sql="SELECT 2",
        explanation="from llm",
        confidence=SQLGenerationConfidence.HIGH,
    )
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=llm_result)

    loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
    match_use_case = MatchTrustedSQLUseCase(loader, TrustedSQLMatcher(), settings=settings)

    use_case = GenerateSQLUseCase(
        BuildSchemaContextUseCase(mock_repository),
        mock_generator,
        settings,
        match_trusted=match_use_case,
    )

    await use_case.execute(
        GenerateSQLRequest(
            question="How many kids are in the Example classroom?",
            use_llm=True,
        ),
    )

    mock_generator.generate.assert_awaited_once()
    gen_call: SQLGenerationRequest = mock_generator.generate.await_args.args[0]
    assert gen_call.question.startswith("How many kids")
