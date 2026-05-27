"""Load ``GovernancePolicyCatalog`` from YAML (Phase 12.2 / 12.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from insightai.domain.exceptions import GovernancePolicyError
from insightai.domain.models.governance import (
    ColumnMaskStrategy,
    GovernancePolicyCatalog,
    MaskRule,
    MissingAttributeAction,
    RolePolicy,
    ScopeBindingOperator,
    ScopeDimension,
    SqlScopeBinding,
    TablePolicy,
)
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

_POLICIES_FILE = "policies.yaml"


class YamlGovernancePolicyLoader:
    """Load governance policy from ``config/governance/policies.yaml``."""

    def __init__(self, governance_dir: Path) -> None:
        self._governance_dir = governance_dir.resolve()
        self._catalog: GovernancePolicyCatalog | None = None

    def load(self) -> GovernancePolicyCatalog:
        if self._catalog is not None:
            return self._catalog
        self._catalog = self._load_from_disk()
        return self._catalog

    def reload(self) -> GovernancePolicyCatalog:
        self._catalog = None
        return self.load()

    def _load_from_disk(self) -> GovernancePolicyCatalog:
        path = self._governance_dir / _POLICIES_FILE
        if not path.is_file():
            msg = f"Governance policy file not found: {path}"
            raise GovernancePolicyError(msg)
        raw = _read_yaml(path)
        catalog = _parse_catalog(raw)
        logger.info(
            "governance_catalog_loaded",
            path=str(path),
            enabled=catalog.enabled,
            dimension_count=len(catalog.scope_dimensions),
            role_count=len(catalog.roles),
        )
        return catalog


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        msg = f"Expected mapping in {path}, got {type(data).__name__}"
        raise GovernancePolicyError(msg)
    return data


def _parse_catalog(raw: dict[str, Any]) -> GovernancePolicyCatalog:
    enabled = bool(raw.get("enabled", True))
    default_missing = _parse_missing_action(
        raw.get("default_missing_attribute_action"),
        default=MissingAttributeAction.DENY,
    )
    dimensions = _parse_scope_dimensions(raw.get("scope_dimensions"))
    roles = _parse_roles(raw.get("roles"))
    return GovernancePolicyCatalog(
        scope_dimensions=dimensions,
        roles=roles,
        default_missing_attribute_action=default_missing,
        enabled=enabled,
    )


def _parse_scope_dimensions(raw: object) -> dict[str, ScopeDimension]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"scope_dimensions must be a mapping, got {type(raw).__name__}"
        raise GovernancePolicyError(msg)
    out: dict[str, ScopeDimension] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            msg = f"scope_dimensions[{key!r}] must be a mapping, got {type(value).__name__}"
            raise GovernancePolicyError(msg)
        bindings_raw = value.get("sql_bindings") or []
        bindings: list[SqlScopeBinding] = []
        if isinstance(bindings_raw, list):
            for item in bindings_raw:
                if isinstance(item, dict):
                    bindings.append(_parse_binding(item))
        out[str(key).strip().lower()] = ScopeDimension(
            id=str(key).strip().lower(),
            description=str(value.get("description") or ""),
            sql_bindings=bindings,
        )
    return out


def _parse_binding(raw: dict[str, Any]) -> SqlScopeBinding:
    operator_raw = str(raw.get("operator", ScopeBindingOperator.IN_PRINCIPAL_ATTRIBUTE.value))
    try:
        operator = ScopeBindingOperator(operator_raw.strip().lower())
    except ValueError as exc:
        msg = f"Unknown scope binding operator: {operator_raw!r}"
        raise GovernancePolicyError(msg) from exc
    return SqlScopeBinding(
        table=str(raw["table"]),
        column=str(raw["column"]),
        operator=operator,
        attribute=str(raw["attribute"]),
    )


def _parse_roles(raw: object) -> dict[str, RolePolicy]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"roles must be a mapping, got {type(raw).__name__}"
        raise GovernancePolicyError(msg)
    out: dict[str, RolePolicy] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            msg = f"roles[{key!r}] must be a mapping, got {type(value).__name__}"
            raise GovernancePolicyError(msg)
        allowed = value.get("allowed_tables") or ["*"]
        if isinstance(allowed, str):
            allowed = [allowed]
        denied = value.get("denied_table_patterns") or value.get("denied_tables") or []
        if isinstance(denied, str):
            denied = [denied]
        masks_raw = value.get("column_masks") or []
        masks: list[MaskRule] = []
        if isinstance(masks_raw, list):
            for mask in masks_raw:
                if isinstance(mask, str):
                    masks.append(MaskRule(column=mask.strip(), strategy=ColumnMaskStrategy.EXCLUDE))
                elif isinstance(mask, dict):
                    masks.append(_parse_mask(mask))
        scope_raw = value.get("apply_scope_dimensions", value.get("apply_scope"))
        out[str(key).strip().lower()] = RolePolicy(
            role=str(key).strip().lower(),
            table_policy=TablePolicy(
                allowed_tables=[str(t) for t in allowed],
                denied_table_patterns=[str(t) for t in denied],
            ),
            apply_scope_dimensions=_parse_string_list(scope_raw),
            column_masks=masks,
            missing_attribute_action=_parse_missing_action(
                value.get("missing_attribute_action"),
                default=MissingAttributeAction.DENY,
            ),
        )
    return out


def _parse_mask(raw: dict[str, Any]) -> MaskRule:
    strategy_raw = str(raw.get("strategy", ColumnMaskStrategy.EXCLUDE.value))
    try:
        strategy = ColumnMaskStrategy(strategy_raw.strip().lower())
    except ValueError as exc:
        msg = f"Unknown column mask strategy: {strategy_raw!r}"
        raise GovernancePolicyError(msg) from exc
    return MaskRule(column=str(raw["column"]), strategy=strategy)


def _parse_string_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip().lower() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip().lower() for item in raw if str(item).strip()]
    return []


def _parse_missing_action(
    raw: object,
    *,
    default: MissingAttributeAction,
) -> MissingAttributeAction:
    if raw is None:
        return default
    try:
        return MissingAttributeAction(str(raw).strip().lower())
    except ValueError as exc:
        msg = f"Invalid missing_attribute_action: {raw!r}"
        raise GovernancePolicyError(msg) from exc
