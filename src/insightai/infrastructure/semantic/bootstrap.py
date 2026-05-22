"""Trusted semantic layer bootstrap (Phase 11)."""

from __future__ import annotations

from dataclasses import dataclass

from insightai.application.use_cases.match_trusted_sql import MatchTrustedSQLUseCase
from insightai.domain.ports.semantic_catalog_loader import ISemanticCatalogLoader
from insightai.domain.ports.trusted_sql_matcher import ITrustedSQLMatcher
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.logging.setup import get_logger
from insightai.infrastructure.semantic.trusted_matcher import TrustedSQLMatcher
from insightai.infrastructure.semantic.yaml_loader import YamlSemanticCatalogLoader

logger = get_logger(__name__)


@dataclass(frozen=True)
class SemanticComponents:
    """Semantic catalog loader and matcher for the process lifetime."""

    catalog_loader: ISemanticCatalogLoader
    matcher: ITrustedSQLMatcher
    match_use_case: MatchTrustedSQLUseCase
    semantic_path: str
    enabled: bool


def build_semantic_components(settings: Settings) -> SemanticComponents:
    """Wire YAML catalog + rule-based matcher (catalog load is lazy on first match)."""
    path = settings.resolved_semantic_path()
    loader = YamlSemanticCatalogLoader(path)
    matcher = TrustedSQLMatcher()
    match_use_case = MatchTrustedSQLUseCase(loader, matcher, settings)
    logger.info(
        "semantic_configured",
        enabled=settings.semantic_enabled,
        path=str(path),
    )
    return SemanticComponents(
        catalog_loader=loader,
        matcher=matcher,
        match_use_case=match_use_case,
        semantic_path=str(path),
        enabled=settings.semantic_enabled,
    )
