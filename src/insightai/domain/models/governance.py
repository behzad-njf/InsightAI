"""Governance & data policy domain models (Phase 12.1).

Policies are industry-agnostic: scope dimension names, table/column bindings, and role
rules are declared per deployment in ``config/governance/policies.yaml`` (step 12.3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from insightai.domain.models.api_key import ApiKey
    from insightai.domain.models.auth import AuthenticatedPrincipal


class ScopeBindingOperator(StrEnum):
    """How a SQL scope binding resolves principal attributes."""

    IN_PRINCIPAL_ATTRIBUTE = "in_principal_attribute"


class MissingAttributeAction(StrEnum):
    """When a required scope attribute is absent on the principal."""

    DENY = "deny"
    EMPTY_SAFE = "empty_safe"


class ColumnMaskStrategy(StrEnum):
    """How to treat a sensitive column in the SELECT list (step 12.2+)."""

    EXCLUDE = "exclude"
    NULL_LITERAL = "null_literal"
    HASH = "hash"


class PolicyDecisionKind(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class SqlScopeBinding(BaseModel):
    """Maps a scope dimension to a table/column filter via principal attributes."""

    table: str = Field(min_length=1, description="Qualified or bare table name.")
    column: str = Field(min_length=1)
    operator: ScopeBindingOperator = ScopeBindingOperator.IN_PRINCIPAL_ATTRIBUTE
    attribute: str = Field(
        min_length=1,
        description="Key on principal.attributes, e.g. campus_ids.",
    )

    model_config = {"frozen": True}

    @field_validator("table", "column", "attribute", mode="before")
    @classmethod
    def strip_non_empty(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            msg = "table, column, and attribute must be non-empty"
            raise ValueError(msg)
        return text


class ScopeDimension(BaseModel):
    """
    Named scope axis (customer-defined), e.g. ``campus`` or ``store``.

    Not hardcoded in platform code — only referenced from YAML policy.
    """

    id: str = Field(min_length=1, description="Stable dimension id used in role policies.")
    description: str = ""
    sql_bindings: list[SqlScopeBinding] = Field(default_factory=list)

    model_config = {"frozen": True}

    @field_validator("id", mode="before")
    @classmethod
    def normalize_id(cls, value: object) -> str:
        text = str(value).strip().lower()
        if not text:
            msg = "scope dimension id must be non-empty"
            raise ValueError(msg)
        return text


class RowFilterRule(BaseModel):
    """Resolved row filter for one binding + principal attribute values (runtime)."""

    dimension_id: str
    table: str
    column: str
    operator: ScopeBindingOperator = ScopeBindingOperator.IN_PRINCIPAL_ATTRIBUTE
    values: tuple[str, ...] = ()

    model_config = {"frozen": True}

    @property
    def is_restrictive(self) -> bool:
        return bool(self.values)


class MaskRule(BaseModel):
    """Column mask applied to SELECT output for a role."""

    column: str = Field(min_length=1, description="Column name or alias to mask.")
    strategy: ColumnMaskStrategy = ColumnMaskStrategy.EXCLUDE

    model_config = {"frozen": True}

    @field_validator("column", mode="before")
    @classmethod
    def strip_column(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            msg = "mask column must be non-empty"
            raise ValueError(msg)
        return text


class TablePolicy(BaseModel):
    """Table allow/deny patterns for a role (glob-style ``*`` supported in 12.2)."""

    allowed_tables: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed table patterns; * = all.",
    )
    denied_table_patterns: list[str] = Field(
        default_factory=list,
        description="Optional deny patterns (e.g. payroll_*).",
    )

    model_config = {"frozen": True}


class RolePolicy(BaseModel):
    """Governance rules bound to a named role (matches API key roles)."""

    role: str = Field(min_length=1)
    table_policy: TablePolicy = Field(default_factory=TablePolicy)
    apply_scope_dimensions: list[str] = Field(
        default_factory=list,
        description="Scope dimension ids to enforce for this role.",
    )
    column_masks: list[MaskRule] = Field(default_factory=list)
    missing_attribute_action: MissingAttributeAction = MissingAttributeAction.DENY

    model_config = {"frozen": True}

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> str:
        return str(value).strip().lower()

    @field_validator("apply_scope_dimensions", mode="before")
    @classmethod
    def normalize_dimension_ids(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip().lower() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        msg = (
            "apply_scope_dimensions must be a list or comma-separated string, "
            f"got {type(value)!r}"
        )
        raise TypeError(msg)


class GovernancePolicyCatalog(BaseModel):
    """Loaded governance policy for one InsightAI instance (from YAML in step 12.3)."""

    scope_dimensions: dict[str, ScopeDimension] = Field(default_factory=dict)
    roles: dict[str, RolePolicy] = Field(default_factory=dict)
    default_missing_attribute_action: MissingAttributeAction = MissingAttributeAction.DENY
    enabled: bool = True

    model_config = {"frozen": True}

    def role_policy_for(self, role: str) -> RolePolicy | None:
        return self.roles.get(role.strip().lower())

    def dimension(self, dimension_id: str) -> ScopeDimension | None:
        return self.scope_dimensions.get(dimension_id.strip().lower())


class Principal(BaseModel):
    """
    Caller identity for governance and audit.

    Populated from API keys (Phase 16) or JWT; attributes feed scope dimensions.
    """

    subject: str = Field(description="Human label, JWT sub, or stable id.")
    auth_method: str = "api_key"
    api_key_id: str | None = Field(
        default=None,
        description="App DB key UUID when authenticated via stored API key.",
    )
    roles: tuple[str, ...] = ()
    attributes: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    model_config = {"frozen": True}

    @classmethod
    def from_api_key(cls, key: ApiKey) -> Self:
        return cls(
            subject=key.label,
            auth_method="api_key",
            api_key_id=key.id,
            roles=tuple(key.roles),
            attributes={name: tuple(values) for name, values in key.attributes.items()},
        )

    @classmethod
    def from_authenticated_principal(cls, principal: AuthenticatedPrincipal) -> Self | None:
        from insightai.domain.models.auth import ApiAuthMode

        if principal.auth_method == ApiAuthMode.NONE:
            return None
        return cls(
            subject=principal.subject,
            auth_method=str(principal.auth_method),
            api_key_id=principal.api_key_id,
            roles=principal.roles,
            attributes=dict(principal.attributes),
        )

    def has_role(self, role: str) -> bool:
        return role.strip().lower() in self.roles

    def attribute_values(self, attribute: str) -> tuple[str, ...]:
        return self.attributes.get(attribute, ())

    def primary_role(self) -> str | None:
        return self.roles[0] if self.roles else None


# Phase 16 name — same type as Principal (pipeline + request state).
GovernanceContext = Principal


class PolicyDecision(BaseModel):
    """Outcome of evaluating governance for one SQL statement."""

    kind: PolicyDecisionKind
    sql: str | None = Field(
        default=None,
        description="SQL safe to execute when kind=allow.",
    )
    message: str = Field(
        default="",
        description="Operator-safe message when kind=deny (no SQL leak).",
    )
    reason_code: str = "GOVERNANCE_DENIED"
    dimensions_applied: tuple[str, ...] = ()
    column_masks_applied: tuple[str, ...] = ()
    row_filters_applied: tuple[RowFilterRule, ...] = ()

    model_config = {"frozen": True}

    @property
    def allowed(self) -> bool:
        return self.kind == PolicyDecisionKind.ALLOW

    @classmethod
    def allow(
        cls,
        sql: str,
        *,
        dimensions_applied: tuple[str, ...] = (),
        column_masks_applied: tuple[str, ...] = (),
        row_filters_applied: tuple[RowFilterRule, ...] = (),
    ) -> Self:
        return cls(
            kind=PolicyDecisionKind.ALLOW,
            sql=sql.strip(),
            dimensions_applied=dimensions_applied,
            column_masks_applied=column_masks_applied,
            row_filters_applied=row_filters_applied,
        )

    @classmethod
    def deny(
        cls,
        message: str = "Access denied by data policy.",
        *,
        reason_code: str = "GOVERNANCE_DENIED",
    ) -> Self:
        return cls(
            kind=PolicyDecisionKind.DENY,
            message=message.strip() or "Access denied by data policy.",
            reason_code=reason_code,
        )


class GovernanceDecision(BaseModel):
    """
    Enforcer return type (Phase 16 port compatibility).

    Wraps ``PolicyDecision`` for the ask pipeline until all callers use PolicyDecision.
    """

    sql: str
    applied: bool = False
    dimensions_applied: tuple[str, ...] = ()
    column_masks_applied: tuple[str, ...] = ()
    policy: PolicyDecision | None = None

    model_config = {"frozen": True}

    @classmethod
    def from_policy(cls, decision: PolicyDecision) -> Self:
        if not decision.allowed or not decision.sql:
            msg = decision.message or "Access denied by data policy."
            raise ValueError(msg)
        return cls(
            sql=decision.sql,
            applied=bool(
                decision.dimensions_applied
                or decision.column_masks_applied
                or decision.row_filters_applied,
            ),
            dimensions_applied=decision.dimensions_applied,
            column_masks_applied=decision.column_masks_applied,
            policy=decision,
        )

    @classmethod
    def passthrough(cls, sql: str) -> Self:
        return cls(
            sql=sql,
            applied=False,
            policy=PolicyDecision.allow(sql),
        )
