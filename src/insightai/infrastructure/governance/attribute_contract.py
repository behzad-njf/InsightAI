"""Principal attribute contract helpers (Phase 12.5)."""

from __future__ import annotations

from insightai.domain.models.governance import (
    GovernancePolicyCatalog,
    MissingAttributeAction,
    Principal,
)


def required_attributes_for_roles(
    catalog: GovernancePolicyCatalog,
) -> dict[str, frozenset[str]]:
    """
    Map each role to attribute names required by its scope dimensions.

    Only includes roles where ``missing_attribute_action`` is ``deny`` (catalog default
    or per-role override).
    """
    required: dict[str, set[str]] = {}
    for role_name, role in catalog.roles.items():
        missing_action = role.missing_attribute_action
        if missing_action != MissingAttributeAction.DENY:
            if catalog.default_missing_attribute_action != MissingAttributeAction.DENY:
                continue
        attrs: set[str] = set()
        for dim_id in role.apply_scope_dimensions:
            dimension = catalog.dimension(dim_id)
            if dimension is None:
                continue
            for binding in dimension.sql_bindings:
                attrs.add(binding.attribute)
        if attrs:
            required.setdefault(role_name, set()).update(attrs)
    return {role: frozenset(names) for role, names in required.items()}


def validate_key_attributes_for_catalog(
    roles: list[str],
    attributes: dict[str, list[str]],
    catalog: GovernancePolicyCatalog,
) -> list[str]:
    """
    Validate API key roles/attributes against policy before issuing a key.

    Returns human-readable errors (empty when valid).
    """
    errors: list[str] = []
    required_by_role = required_attributes_for_roles(catalog)
    for role in roles:
        role_key = role.strip().lower()
        needed = required_by_role.get(role_key)
        if not needed:
            continue
        for attr in sorted(needed):
            values = attributes.get(attr) or []
            if not values:
                errors.append(
                    f"role {role_key!r} requires attribute {attr!r} "
                    f"(scope dimension binding in policies.yaml)",
                )
    unknown_roles = [
        role.strip().lower()
        for role in roles
        if role.strip().lower() not in catalog.roles
    ]
    if catalog.enabled and unknown_roles and catalog.roles:
        for role in unknown_roles:
            errors.append(
                f"role {role!r} is not defined in policies.yaml "
                f"(defined: {', '.join(sorted(catalog.roles))})",
            )
    return errors


def validate_principal_attributes(
    principal: Principal | None,
    catalog: GovernancePolicyCatalog,
) -> list[str]:
    """Check an authenticated principal has attributes required by its roles."""
    if principal is None or not catalog.enabled:
        return []
    errors: list[str] = []
    required_by_role = required_attributes_for_roles(catalog)
    for role in principal.roles:
        needed = required_by_role.get(role)
        if not needed:
            continue
        for attr in sorted(needed):
            if not principal.attribute_values(attr):
                errors.append(
                    f"principal missing required attribute {attr!r} for role {role!r}",
                )
    return errors
