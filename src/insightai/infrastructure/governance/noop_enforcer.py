"""No-op governance enforcer until Phase 12 policies ship."""

from __future__ import annotations

from insightai.domain.models.governance import GovernanceContext, GovernanceDecision


class NoOpGovernanceEnforcer:
    """Pass SQL through unchanged; records that governance was not applied."""

    def enforce(self, sql: str, context: GovernanceContext | None) -> GovernanceDecision:
        _ = context
        return GovernanceDecision(sql=sql, applied=False)
