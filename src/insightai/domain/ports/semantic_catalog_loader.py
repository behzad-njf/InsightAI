"""Semantic catalog loader port — trusted metrics and example queries (Phase 11)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insightai.domain.models.semantic import SemanticCatalog


class ISemanticCatalogLoader(ABC):
    """Loads approved semantic assets from instance configuration (YAML)."""

    @abstractmethod
    def load(self) -> SemanticCatalog:
        """Return the semantic catalog (cached after first load unless ``reload``)."""

    @abstractmethod
    def reload(self) -> SemanticCatalog:
        """Force reload from disk."""
