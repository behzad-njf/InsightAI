"""SQL governance enforcer — sqlglot scope filters and column masks (Phase 12.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.exceptions import GovernanceDeniedError
from insightai.domain.models.governance import (
    GovernanceContext,
    GovernanceDecision,
    GovernancePolicyCatalog,
    MissingAttributeAction,
    PolicyDecision,
    Principal,
)
from insightai.infrastructure.governance.policy_resolver import (
    merge_role_policies,
    resolve_row_filters,
)
from insightai.infrastructure.governance.sql_transform import transform_select_sql

if TYPE_CHECKING:
    from insightai.domain.models.database import DatabaseKind


class SqlGovernanceEnforcer:
    """Apply ``GovernancePolicyCatalog`` to read-only SELECT statements."""

    def __init__(
        self,
        catalog: GovernancePolicyCatalog,
        *,
        database_kind: DatabaseKind,
    ) -> None:
        self._catalog = catalog
        self._kind = database_kind

    def evaluate(self, sql: str, principal: Principal | None) -> PolicyDecision:
        if not self._catalog.enabled:
            return PolicyDecision.allow(sql)

        if principal is None:
            return PolicyDecision.allow(sql)

        effective = merge_role_policies(self._catalog, principal)
        if effective is None:
            return PolicyDecision.allow(sql)

        filters, missing_deny = resolve_row_filters(self._catalog, principal, effective)
        if missing_deny == MissingAttributeAction.DENY:
            return PolicyDecision.deny(
                "Missing required scope attributes for this API key.",
                reason_code="GOVERNANCE_MISSING_SCOPE",
            )

        try:
            governed_sql, dimensions, masks_applied = transform_select_sql(
                sql,
                kind=self._kind,
                filters=filters,
                masks=effective.column_masks,
                allowed_tables=effective.allowed_tables,
                denied_patterns=effective.denied_table_patterns,
            )
        except ValueError as exc:
            return PolicyDecision.deny(str(exc))

        return PolicyDecision.allow(
            governed_sql,
            dimensions_applied=dimensions,
            column_masks_applied=masks_applied,
            row_filters_applied=filters,
        )

    def enforce(
        self,
        sql: str,
        context: GovernanceContext | None,
    ) -> GovernanceDecision:
        principal = context
        decision = self.evaluate(sql, principal)
        if not decision.allowed:
            raise GovernanceDeniedError(decision.message)
        return GovernanceDecision.from_policy(decision)
