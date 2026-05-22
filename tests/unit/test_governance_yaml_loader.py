"""Unit tests for governance YAML loader (Phase 12.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.exceptions import GovernancePolicyError
from insightai.domain.models.governance import ColumnMaskStrategy, MissingAttributeAction
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "governance"


def test_loads_roles_and_dimensions() -> None:
    catalog = YamlGovernancePolicyLoader(FIXTURE_DIR).load()
    assert catalog.enabled is True
    assert catalog.dimension("campus") is not None
    analyst = catalog.role_policy_for("analyst")
    assert analyst is not None
    assert analyst.apply_scope_dimensions == ["campus"]
    assert analyst.column_masks[0].strategy == ColumnMaskStrategy.EXCLUDE
    assert catalog.default_missing_attribute_action == MissingAttributeAction.DENY


def test_missing_policies_file_raises() -> None:
    with pytest.raises(GovernancePolicyError, match="not found"):
        YamlGovernancePolicyLoader(Path("/nonexistent/governance")).load()
