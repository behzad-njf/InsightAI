"""Resolve effective governance rules from principal + catalog (Phase 12.2)."""

from __future__ import annotations

from dataclasses import dataclass

from insightai.domain.models.governance import (
    ColumnMaskStrategy,
    GovernancePolicyCatalog,
    MaskRule,
    MissingAttributeAction,
    Principal,
    RolePolicy,
    RowFilterRule,
    ScopeBindingOperator,
    ScopeDimension,
)


@dataclass(frozen=True)
class EffectiveRolePolicy:
    """Merged policy across all roles assigned to the principal."""

    roles: tuple[str, ...]
    apply_scope_dimensions: tuple[str, ...]
    column_masks: tuple[MaskRule, ...]
    allowed_tables: tuple[str, ...]
    denied_table_patterns: tuple[str, ...]
    missing_attribute_action: MissingAttributeAction


def merge_role_policies(
    catalog: GovernancePolicyCatalog,
    principal: Principal,
) -> EffectiveRolePolicy | None:
    """Combine policies for every role on the principal (union of scopes/masks)."""
    matched: list[RolePolicy] = []
    for role in principal.roles:
        policy = catalog.role_policy_for(role)
        if policy is not None:
            matched.append(policy)

    if not matched:
        return None

    scope_ids: list[str] = []
    masks: dict[str, MaskRule] = {}
    allowed: list[str] = []
    denied: list[str] = []
    missing_action = catalog.default_missing_attribute_action
    any_wildcard_allowed = False

    for policy in matched:
        for dim_id in policy.apply_scope_dimensions:
            if dim_id not in scope_ids:
                scope_ids.append(dim_id)
        for mask in policy.column_masks:
            masks[mask.column.lower()] = mask
        tp = policy.table_policy
        if any(p.strip() == "*" for p in tp.allowed_tables):
            any_wildcard_allowed = True
        for pattern in tp.allowed_tables:
            if pattern not in allowed:
                allowed.append(pattern)
        for pattern in tp.denied_table_patterns:
            if pattern not in denied:
                denied.append(pattern)
        if policy.missing_attribute_action == MissingAttributeAction.DENY:
            missing_action = MissingAttributeAction.DENY

    if any_wildcard_allowed:
        allowed = ["*"]

    return EffectiveRolePolicy(
        roles=tuple(p.role for p in matched),
        apply_scope_dimensions=tuple(scope_ids),
        column_masks=tuple(masks.values()),
        allowed_tables=tuple(allowed),
        denied_table_patterns=tuple(denied),
        missing_attribute_action=missing_action,
    )


def resolve_row_filters(
    catalog: GovernancePolicyCatalog,
    principal: Principal,
    effective: EffectiveRolePolicy,
) -> tuple[tuple[RowFilterRule, ...], MissingAttributeAction | None]:
    """
    Build row filter rules from scope dimensions.

    Returns filters and optional deny reason when ``missing_attribute_action`` is deny
    and a required attribute is absent.
    """
    filters: list[RowFilterRule] = []
    for dim_id in effective.apply_scope_dimensions:
        dimension = catalog.dimension(dim_id)
        if dimension is None:
            continue
        for binding in dimension.sql_bindings:
            if binding.operator != ScopeBindingOperator.IN_PRINCIPAL_ATTRIBUTE:
                continue
            values = principal.attribute_values(binding.attribute)
            if not values:
                if effective.missing_attribute_action == MissingAttributeAction.DENY:
                    return (), MissingAttributeAction.DENY
                filters.append(
                    RowFilterRule(
                        dimension_id=dim_id,
                        table=binding.table,
                        column=binding.column,
                        operator=binding.operator,
                        values=(),
                    ),
                )
                continue
            filters.append(
                RowFilterRule(
                    dimension_id=dim_id,
                    table=binding.table,
                    column=binding.column,
                    operator=binding.operator,
                    values=values,
                ),
            )
    return tuple(filters), None
