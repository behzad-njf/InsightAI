"""Governance enforcement port (Phase 16.5 stub; Phase 12 implementation)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from insightai.domain.models.governance import GovernanceContext, GovernanceDecision


class IGovernanceEnforcer(Protocol):
    """Rewrite or deny SQL based on principal roles and scope attributes."""

    def enforce(self, sql: str, context: GovernanceContext | None) -> GovernanceDecision:
        """
        Return SQL safe to execute for ``context``.

        Implementations evaluate ``GovernancePolicyCatalog`` (step 12.2+) and return
        ``GovernanceDecision.from_policy(PolicyDecision.allow(...))`` or raise
        ``GovernanceDeniedError`` on deny.
        """
