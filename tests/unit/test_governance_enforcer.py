"""Unit tests for Phase 12.2 SQL governance enforcer."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.domain.exceptions import GovernanceDeniedError
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.governance import (
    GovernancePolicyCatalog,
    Principal,
    RolePolicy,
    ScopeDimension,
    SqlScopeBinding,
    TablePolicy,
)
from insightai.infrastructure.governance.enforcer import SqlGovernanceEnforcer
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

FIXTURE_GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "governance"


def _catalog(*, enabled: bool = True) -> GovernancePolicyCatalog:
    loader = YamlGovernancePolicyLoader(FIXTURE_GOVERNANCE_DIR)
    catalog = loader.load()
    if enabled == catalog.enabled:
        return catalog
    return catalog.model_copy(update={"enabled": enabled})


def _enforcer(catalog: GovernancePolicyCatalog | None = None) -> SqlGovernanceEnforcer:
    return SqlGovernanceEnforcer(
        catalog or _catalog(),
        database_kind=DatabaseKind.SQLITE,
    )


def _analyst_principal(*, campus_ids: tuple[str, ...] = ("1", "2")) -> Principal:
    return Principal(
        subject="Example analyst",
        auth_method="api_key",
        api_key_id="00000000-0000-0000-0000-000000000001",
        roles=("analyst",),
        attributes={"campus_ids": campus_ids},
    )


def test_yaml_loader_reads_fixture() -> None:
    catalog = _catalog()
    assert catalog.enabled is True
    assert "campus" in catalog.scope_dimensions
    assert catalog.role_policy_for("analyst") is not None


def test_injects_campus_scope_filter_without_table_alias() -> None:
    sql = "SELECT id FROM school_school"
    decision = _enforcer().evaluate(sql, _analyst_principal())
    assert decision.allowed
    assert decision.sql is not None
    assert "WHERE" in decision.sql.upper()
    assert "school_school" in decision.sql.lower()
    assert "1" in decision.sql


def test_injects_campus_scope_filter() -> None:
    sql = "SELECT s.id, s.name FROM school_school AS s"
    decision = _enforcer().evaluate(sql, _analyst_principal())
    assert decision.allowed
    assert decision.sql is not None
    assert "school_school" in decision.sql.lower()
    assert "1" in decision.sql
    assert "2" in decision.sql
    assert "campus" in decision.dimensions_applied


def test_denies_missing_campus_ids() -> None:
    principal = _analyst_principal(campus_ids=())
    with pytest.raises(GovernanceDeniedError, match="scope attributes"):
        _enforcer().enforce(
            "SELECT s.id FROM school_school AS s",
            principal,
        )


def test_masks_exclude_sensitive_columns() -> None:
    sql = "SELECT s.id, s.email, s.phone FROM school_school AS s"
    decision = _enforcer().evaluate(sql, _analyst_principal())
    assert decision.allowed
    assert decision.sql is not None
    lowered = decision.sql.lower()
    assert "email" not in lowered.split("from")[0]
    assert "phone" not in lowered.split("from")[0]
    assert "email" in decision.column_masks_applied
    assert "phone" in decision.column_masks_applied


def test_denies_disallowed_table() -> None:
    principal = Principal(
        subject="Restricted",
        roles=("restricted",),
        attributes={},
    )
    with pytest.raises(GovernanceDeniedError, match="not permitted"):
        _enforcer().enforce(
            "SELECT e.id FROM enrollment AS e",
            principal,
        )


def test_admin_passthrough_without_scope() -> None:
    sql = "SELECT s.id, s.email FROM school_school AS s"
    principal = Principal(subject="Admin", roles=("admin",))
    decision = _enforcer().evaluate(sql, principal)
    assert decision.allowed
    assert decision.sql is not None
    assert "email" in decision.sql.lower()


def test_catalog_disabled_passthrough() -> None:
    enforcer = _enforcer(_catalog(enabled=False))
    sql = "SELECT secret FROM payroll_data"
    decision = enforcer.evaluate(sql, _analyst_principal())
    assert decision.allowed
    assert decision.sql == sql.strip()


def test_no_matching_role_passthrough() -> None:
    principal = Principal(subject="Guest", roles=("viewer",))
    sql = "SELECT 1"
    decision = _enforcer().evaluate(sql, principal)
    assert decision.allowed
    assert decision.sql == sql


def test_build_governance_components_uses_noop_when_disabled() -> None:
    from insightai.infrastructure.config.settings import Settings
    from insightai.infrastructure.governance.bootstrap import build_governance_components
    from insightai.infrastructure.governance.noop_enforcer import NoOpGovernanceEnforcer

    components = build_governance_components(
        Settings(governance_enabled=False),
    )
    assert components.enabled is False
    assert isinstance(components.enforcer, NoOpGovernanceEnforcer)


def test_build_governance_components_loads_sql_enforcer() -> None:
    from insightai.infrastructure.config.settings import Settings
    from insightai.infrastructure.governance.bootstrap import build_governance_components

    settings = Settings(
        governance_enabled=True,
        governance_path=FIXTURE_GOVERNANCE_DIR,
        database_kind=DatabaseKind.SQLITE,
    )
    components = build_governance_components(settings)
    assert components.enabled is True
    decision = components.enforcer.enforce(
        "SELECT s.id FROM school_school AS s",
        _analyst_principal(),
    )
    assert "1" in decision.sql


def test_custom_catalog_table_deny() -> None:
    catalog = GovernancePolicyCatalog(
        enabled=True,
        scope_dimensions={},
        roles={
            "payroll_only": RolePolicy(
                role="payroll_only",
                table_policy=TablePolicy(
                    allowed_tables=["payroll_*"],
                    denied_table_patterns=[],
                ),
            ),
        },
    )
    principal = Principal(subject="Payroll", roles=("payroll_only",))
    with pytest.raises(GovernanceDeniedError):
        SqlGovernanceEnforcer(catalog, database_kind=DatabaseKind.SQLITE).enforce(
            "SELECT s.id FROM school_school AS s",
            principal,
        )


def test_empty_safe_missing_attribute_allows_empty_filter() -> None:
    from insightai.domain.models.governance import MissingAttributeAction

    catalog = GovernancePolicyCatalog(
        enabled=True,
        scope_dimensions={
            "campus": ScopeDimension(
                id="campus",
                sql_bindings=[
                    SqlScopeBinding(
                        table="school_school",
                        column="id",
                        attribute="campus_ids",
                    ),
                ],
            ),
        },
        roles={
            "analyst": RolePolicy(
                role="analyst",
                apply_scope_dimensions=["campus"],
                missing_attribute_action=MissingAttributeAction.EMPTY_SAFE,
            ),
        },
        default_missing_attribute_action=MissingAttributeAction.EMPTY_SAFE,
    )
    principal = Principal(subject="Analyst", roles=("analyst",), attributes={})
    decision = SqlGovernanceEnforcer(catalog, database_kind=DatabaseKind.SQLITE).evaluate(
        "SELECT s.id FROM school_school AS s",
        principal,
    )
    assert decision.allowed
    assert decision.sql is not None
    assert "FALSE" in decision.sql.upper() or "false" in decision.sql.lower()
