"""Unit tests for MatchTrustedSQLUseCase."""

from __future__ import annotations

from pathlib import Path

from insightai.application.use_cases.match_trusted_sql import MatchTrustedSQLUseCase
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import TrustedSQLMatchRequest
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.semantic.trusted_matcher import TrustedSQLMatcher
from insightai.infrastructure.semantic.yaml_loader import YamlSemanticCatalogLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SEMANTIC_DIR = PROJECT_ROOT / "tests" / "fixtures" / "semantic"


def test_use_case_disabled_returns_no_match() -> None:
    settings = Settings(semantic_enabled=False)
    use_case = MatchTrustedSQLUseCase(
        YamlSemanticCatalogLoader(FIXTURE_SEMANTIC_DIR),
        TrustedSQLMatcher(),
        settings=settings,
    )
    result = use_case.execute(
        TrustedSQLMatchRequest(
            question="how many active users",
            database_kind=DatabaseKind.MSSQL,
        ),
    )
    assert not result.matched


def test_use_case_enabled_matches_fixture() -> None:
    settings = Settings(semantic_enabled=True, semantic_path=FIXTURE_SEMANTIC_DIR)
    loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
    use_case = MatchTrustedSQLUseCase(loader, TrustedSQLMatcher(), settings=settings)
    result = use_case.execute(
        TrustedSQLMatchRequest(
            question="How many kids are in the Example classroom?",
            database_kind=DatabaseKind.MSSQL,
        ),
    )
    assert result.matched
    assert result.asset_id == "fixture_classroom_headcount"
