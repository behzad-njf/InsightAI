"""Unit tests for governance policy validation (Phase 12.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.exceptions import ConfigurationError
from insightai.infrastructure.governance.bootstrap import build_governance_components
from insightai.infrastructure.governance.validator import validate_governance_catalog
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "governance"
CONFIG_DIR = PROJECT_ROOT / "config" / "governance"


def test_validate_fixture_catalog_ok() -> None:
    assert validate_governance_catalog(FIXTURE_DIR) == []


def test_validate_production_template_ok() -> None:
    assert validate_governance_catalog(CONFIG_DIR) == []


def test_apply_scope_alias_and_mask_shorthand(tmp_path: Path) -> None:
    (tmp_path / "policies.yaml").write_text(
        """
enabled: true
scope_dimensions:
  campus:
    sql_bindings:
      - table: school_school
        column: id
        attribute: campus_ids
roles:
  analyst:
    allowed_tables: ["*"]
    apply_scope: [campus]
    column_masks: [email, phone]
""",
        encoding="utf-8",
    )
    assert validate_governance_catalog(tmp_path) == []
    catalog = YamlGovernancePolicyLoader(tmp_path).load()
    role = catalog.role_policy_for("analyst")
    assert role is not None
    assert role.apply_scope_dimensions == ["campus"]
    assert len(role.column_masks) == 2
    assert role.column_masks[0].column == "email"


def test_reports_missing_binding_fields(tmp_path: Path) -> None:
    (tmp_path / "policies.yaml").write_text(
        """
enabled: true
scope_dimensions:
  campus:
    sql_bindings:
      - table: school_school
        column: id
roles:
  analyst:
    allowed_tables: ["*"]
""",
        encoding="utf-8",
    )
    errors = validate_governance_catalog(tmp_path)
    assert any("attribute" in line for line in errors)


def test_reports_unknown_dimension_on_role(tmp_path: Path) -> None:
    (tmp_path / "policies.yaml").write_text(
        """
enabled: true
scope_dimensions:
  campus:
    sql_bindings:
      - table: school_school
        column: id
        attribute: campus_ids
roles:
  analyst:
    allowed_tables: ["*"]
    apply_scope_dimensions: [missing_dim]
""",
        encoding="utf-8",
    )
    errors = validate_governance_catalog(tmp_path)
    assert any("unknown dimension" in line for line in errors)


def test_bootstrap_raises_on_invalid_policy(tmp_path: Path) -> None:
    from insightai.infrastructure.config.settings import Settings
    from insightai.domain.models.database import DatabaseKind

    (tmp_path / "policies.yaml").write_text("enabled: true\nroles: {}\n", encoding="utf-8")
    settings = Settings(
        governance_enabled=True,
        governance_path=tmp_path,
        database_kind=DatabaseKind.SQLITE,
    )
    with pytest.raises(ConfigurationError, match="Invalid governance policy"):
        build_governance_components(settings)
