"""Unit tests for Phase 12.1 governance policy domain models."""

from __future__ import annotations

import pytest

from insightai.domain.models.governance import (
    ColumnMaskStrategy,
    GovernanceContext,
    GovernanceDecision,
    GovernancePolicyCatalog,
    MaskRule,
    MissingAttributeAction,
    PolicyDecision,
    PolicyDecisionKind,
    Principal,
    RolePolicy,
    RowFilterRule,
    ScopeDimension,
    SqlScopeBinding,
    TablePolicy,
)


def test_scope_dimension_normalizes_id() -> None:
    dim = ScopeDimension(
        id=" Campus ",
        sql_bindings=[
            SqlScopeBinding(
                table="school_school",
                column="id",
                attribute="campus_ids",
            ),
        ],
    )
    assert dim.id == "campus"
    assert dim.sql_bindings[0].attribute == "campus_ids"


def test_role_policy_normalizes_role_and_dimensions() -> None:
    role = RolePolicy(
        role=" Analyst ",
        apply_scope_dimensions="campus, store",
        column_masks=[MaskRule(column="email", strategy=ColumnMaskStrategy.EXCLUDE)],
    )
    assert role.role == "analyst"
    assert role.apply_scope_dimensions == ["campus", "store"]


def test_principal_from_attributes() -> None:
    principal = Principal(
        subject="Example analyst",
        roles=("analyst",),
        attributes={"campus_ids": ("1", "2")},
    )
    assert principal.attribute_values("campus_ids") == ("1", "2")
    assert principal.has_role("analyst")


def test_governance_context_is_principal_alias() -> None:
    ctx = GovernanceContext(subject="x", roles=("analyst",))
    assert isinstance(ctx, Principal)


def test_policy_decision_allow_and_deny() -> None:
    allowed = PolicyDecision.allow(
        "SELECT 1",
        dimensions_applied=("campus",),
        column_masks_applied=("email",),
    )
    assert allowed.allowed
    assert allowed.sql == "SELECT 1"

    denied = PolicyDecision.deny("No access to payroll.")
    assert denied.kind == PolicyDecisionKind.DENY
    assert "payroll" in denied.message
    assert denied.sql is None


def test_governance_decision_from_policy() -> None:
    policy = PolicyDecision.allow("SELECT id FROM t", dimensions_applied=("campus",))
    gov = GovernanceDecision.from_policy(policy)
    assert gov.sql == "SELECT id FROM t"
    assert gov.dimensions_applied == ("campus",)
    assert gov.applied is True


def test_governance_decision_from_deny_raises() -> None:
    with pytest.raises(ValueError, match="denied"):
        GovernanceDecision.from_policy(PolicyDecision.deny())


def test_catalog_lookup() -> None:
    catalog = GovernancePolicyCatalog(
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
                table_policy=TablePolicy(allowed_tables=["*"]),
                apply_scope_dimensions=["campus"],
                missing_attribute_action=MissingAttributeAction.DENY,
            ),
        },
    )
    assert catalog.dimension("campus") is not None
    analyst = catalog.role_policy_for("analyst")
    assert analyst is not None
    assert analyst.apply_scope_dimensions == ["campus"]


def test_row_filter_rule_restrictive() -> None:
    empty = RowFilterRule(dimension_id="campus", table="t", column="id", values=())
    assert not empty.is_restrictive
    scoped = RowFilterRule(dimension_id="campus", table="t", column="id", values=("1",))
    assert scoped.is_restrictive
