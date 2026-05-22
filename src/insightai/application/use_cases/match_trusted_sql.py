"""Match questions or SQL against the trusted semantic catalog (Phase 11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.semantic import (
    SemanticCatalog,
    TrustedSQLMatchRequest,
    TrustedSQLMatchResult,
)
from insightai.infrastructure.semantic.yaml_loader import empty_semantic_catalog

if TYPE_CHECKING:
    from insightai.domain.ports.semantic_catalog_loader import ISemanticCatalogLoader
    from insightai.domain.ports.trusted_sql_matcher import ITrustedSQLMatcher
    from insightai.infrastructure.config.settings import Settings


class MatchTrustedSQLUseCase:
    """Load semantic catalog (when enabled) and run rule-based trusted matching."""

    def __init__(
        self,
        catalog_loader: ISemanticCatalogLoader,
        matcher: ITrustedSQLMatcher,
        settings: Settings | None = None,
    ) -> None:
        from insightai.infrastructure.config.settings import get_settings

        self._catalog_loader = catalog_loader
        self._matcher = matcher
        self._settings = settings or get_settings()

    def execute(self, request: TrustedSQLMatchRequest) -> TrustedSQLMatchResult:
        if not self._settings.semantic_enabled:
            return TrustedSQLMatchResult.no_match()

        catalog = self._catalog_loader.load()
        if not catalog.enabled_metrics and not catalog.enabled_example_queries:
            return TrustedSQLMatchResult.no_match()

        return self._matcher.match(request, catalog)

    def load_catalog_or_empty(self) -> SemanticCatalog:
        """Expose catalog for tests/admin without matching."""
        if not self._settings.semantic_enabled:
            return empty_semantic_catalog()
        return self._catalog_loader.load()
