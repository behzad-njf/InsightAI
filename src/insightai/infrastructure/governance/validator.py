"""Governance policy schema and semantic validation (Phase 12.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insightai.domain.exceptions import GovernancePolicyError
from insightai.domain.models.governance import (
    ColumnMaskStrategy,
    GovernancePolicyCatalog,
    MissingAttributeAction,
    ScopeBindingOperator,
)
from insightai.infrastructure.governance.yaml_loader import (
    _POLICIES_FILE,
    _parse_catalog,
    _read_yaml,
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "enabled",
        "scope_dimensions",
        "roles",
        "default_missing_attribute_action",
    },
)
_SCOPE_DIMENSION_KEYS = frozenset({"description", "sql_bindings"})
_BINDING_KEYS = frozenset({"table", "column", "operator", "attribute"})
_ROLE_KEYS = frozenset(
    {
        "allowed_tables",
        "denied_table_patterns",
        "denied_tables",
        "apply_scope_dimensions",
        "apply_scope",
        "column_masks",
        "missing_attribute_action",
    },
)
_MASK_KEYS = frozenset({"column", "strategy"})


def validate_governance_catalog(governance_dir: Path) -> list[str]:
    """
    Validate ``policies.yaml`` structure and catalog semantics.

    Returns human-readable error lines (empty when valid).
    """
    errors: list[str] = []
    root = governance_dir.resolve()
    policy_path = root / _POLICIES_FILE

    if not root.is_dir():
        return [f"Governance directory not found: {root}"]
    if not policy_path.is_file():
        return [f"Missing {_POLICIES_FILE} in {root}"]

    try:
        raw = _read_yaml(policy_path)
    except GovernancePolicyError as exc:
        return [str(exc)]

    errors.extend(_validate_raw_document(raw, source=str(policy_path)))

    try:
        catalog = _parse_catalog(raw)
    except GovernancePolicyError as exc:
        errors.append(str(exc))
        return errors
    except Exception as exc:
        errors.append(f"Failed to parse catalog: {exc}")
        return errors

    errors.extend(_validate_catalog_semantics(catalog))
    return errors


def _validate_raw_document(raw: dict[str, Any], *, source: str) -> list[str]:
    errors: list[str] = []
    for key in raw:
        if key not in _TOP_LEVEL_KEYS:
            errors.append(f"{source}: unknown top-level key {key!r}")

    if "scope_dimensions" in raw:
        errors.extend(_validate_scope_dimensions(raw["scope_dimensions"], source=source))
    if "roles" in raw:
        errors.extend(_validate_roles(raw["roles"], source=source))

    if "default_missing_attribute_action" in raw:
        errors.extend(
            _validate_missing_action(
                raw["default_missing_attribute_action"],
                path=f"{source}:default_missing_attribute_action",
            ),
        )
    return errors


def _validate_scope_dimensions(raw: object, *, source: str) -> list[str]:
    errors: list[str] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        return [f"{source}:scope_dimensions must be a mapping, got {type(raw).__name__}"]
    for dim_id, dim_value in raw.items():
        path = f"{source}:scope_dimensions.{dim_id}"
        if not str(dim_id).strip():
            errors.append(f"{path}: dimension id must be non-empty")
            continue
        if not isinstance(dim_value, dict):
            errors.append(f"{path}: must be a mapping, got {type(dim_value).__name__}")
            continue
        for key in dim_value:
            if key not in _SCOPE_DIMENSION_KEYS:
                errors.append(f"{path}: unknown key {key!r}")
        bindings = dim_value.get("sql_bindings")
        if bindings is None:
            errors.append(f"{path}: sql_bindings is required (use [] if none)")
        elif not isinstance(bindings, list):
            errors.append(f"{path}.sql_bindings: must be a list")
        else:
            for index, item in enumerate(bindings):
                errors.extend(_validate_binding(item, path=f"{path}.sql_bindings[{index}]"))
    return errors


def _validate_binding(raw: object, *, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return [f"{path}: must be a mapping, got {type(raw).__name__}"]
    for key in raw:
        if key not in _BINDING_KEYS:
            errors.append(f"{path}: unknown key {key!r}")
    for required in ("table", "column", "attribute"):
        if required not in raw or not str(raw.get(required, "")).strip():
            errors.append(f"{path}: missing or empty {required!r}")
    if "operator" in raw:
        op = str(raw["operator"]).strip().lower()
        try:
            ScopeBindingOperator(op)
        except ValueError:
            allowed = ", ".join(o.value for o in ScopeBindingOperator)
            errors.append(f"{path}: unknown operator {op!r} (allowed: {allowed})")
    return errors


def _validate_roles(raw: object, *, source: str) -> list[str]:
    errors: list[str] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        return [f"{source}:roles must be a mapping, got {type(raw).__name__}"]
    if not raw:
        errors.append(f"{source}:roles must define at least one role")
    for role_name, role_value in raw.items():
        path = f"{source}:roles.{role_name}"
        if not str(role_name).strip():
            errors.append(f"{path}: role name must be non-empty")
            continue
        if not isinstance(role_value, dict):
            errors.append(f"{path}: must be a mapping, got {type(role_value).__name__}")
            continue
        for key in role_value:
            if key not in _ROLE_KEYS:
                errors.append(f"{path}: unknown key {key!r}")
        allowed = role_value.get("allowed_tables")
        if allowed is not None and isinstance(allowed, list) and len(allowed) == 0:
            errors.append(f"{path}: allowed_tables must not be empty (use ['*'] for all)")
        scope_raw = role_value.get("apply_scope_dimensions", role_value.get("apply_scope"))
        if scope_raw is not None:
            errors.extend(_validate_string_or_list(scope_raw, path=f"{path}.apply_scope_dimensions"))
        masks = role_value.get("column_masks")
        if masks is not None:
            if not isinstance(masks, list):
                errors.append(f"{path}.column_masks: must be a list")
            else:
                for index, mask in enumerate(masks):
                    errors.extend(_validate_mask(mask, path=f"{path}.column_masks[{index}]"))
        if "missing_attribute_action" in role_value:
            errors.extend(
                _validate_missing_action(
                    role_value["missing_attribute_action"],
                    path=f"{path}:missing_attribute_action",
                ),
            )
    return errors


def _validate_mask(raw: object, *, path: str) -> list[str]:
    if isinstance(raw, str):
        if not raw.strip():
            return [f"{path}: column name must be non-empty"]
        return []
    if not isinstance(raw, dict):
        return [f"{path}: must be a string or mapping, got {type(raw).__name__}"]
    errors: list[str] = []
    for key in raw:
        if key not in _MASK_KEYS:
            errors.append(f"{path}: unknown key {key!r}")
    if "column" not in raw or not str(raw.get("column", "")).strip():
        errors.append(f"{path}: missing or empty 'column'")
    if "strategy" in raw:
        strategy = str(raw["strategy"]).strip().lower()
        try:
            ColumnMaskStrategy(strategy)
        except ValueError:
            allowed = ", ".join(s.value for s in ColumnMaskStrategy)
            errors.append(f"{path}: unknown strategy {strategy!r} (allowed: {allowed})")
    return errors


def _validate_string_or_list(raw: object, *, path: str) -> list[str]:
    if isinstance(raw, str):
        if not raw.strip():
            return [f"{path}: must be non-empty when a string"]
        return []
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            if not str(item).strip():
                return [f"{path}[{index}]: must be non-empty"]
        return []
    return [f"{path}: must be a string or list, got {type(raw).__name__}"]


def _validate_missing_action(raw: object, *, path: str) -> list[str]:
    try:
        MissingAttributeAction(str(raw).strip().lower())
    except ValueError:
        allowed = ", ".join(a.value for a in MissingAttributeAction)
        return [f"{path}: invalid value {raw!r} (allowed: {allowed})"]
    return []


def _validate_catalog_semantics(catalog: GovernancePolicyCatalog) -> list[str]:
    errors: list[str] = []
    known_dimensions = set(catalog.scope_dimensions.keys())

    if catalog.enabled and not catalog.roles:
        errors.append("Catalog enabled=true but roles is empty")

    for dim_id, dimension in catalog.scope_dimensions.items():
        if not dimension.sql_bindings:
            errors.append(f"scope_dimensions.{dim_id}: sql_bindings must contain at least one binding")

    for role_name, role in catalog.roles.items():
        for dim_id in role.apply_scope_dimensions:
            if dim_id not in known_dimensions:
                errors.append(
                    f"roles.{role_name}: apply_scope_dimensions references unknown dimension {dim_id!r}",
                )
            else:
                bound = catalog.scope_dimensions[dim_id]
                if not bound.sql_bindings:
                    errors.append(
                        f"roles.{role_name}: dimension {dim_id!r} has no sql_bindings",
                    )

        if not role.table_policy.allowed_tables:
            errors.append(f"roles.{role_name}: allowed_tables must not be empty")

        seen_masks: set[str] = set()
        for mask in role.column_masks:
            key = mask.column.lower()
            if key in seen_masks:
                errors.append(f"roles.{role_name}: duplicate column_masks entry for {mask.column!r}")
            seen_masks.add(key)

    return errors
