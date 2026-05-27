"""Wire governance components (Phase 12.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightai.domain.exceptions import ConfigurationError, GovernancePolicyError
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.governance.enforcer import SqlGovernanceEnforcer
from insightai.infrastructure.governance.noop_enforcer import NoOpGovernanceEnforcer
from insightai.infrastructure.governance.validator import validate_governance_catalog
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from insightai.domain.ports.governance import IGovernanceEnforcer

logger = get_logger(__name__)


@dataclass(frozen=True)
class GovernanceComponents:
    """Bundled governance infrastructure for DI / FastAPI lifespan."""

    enforcer: IGovernanceEnforcer
    enabled: bool = False


def build_governance_components(
    settings: Settings | None = None,
) -> GovernanceComponents:
    """Create governance enforcer (no-op unless ``governance_enabled``)."""
    resolved = settings or get_settings()
    if not resolved.governance_enabled:
        logger.info("governance_disabled", enabled=False)
        return GovernanceComponents(enforcer=NoOpGovernanceEnforcer(), enabled=False)

    policy_dir = resolved.resolved_governance_path()
    validation_errors = validate_governance_catalog(policy_dir)
    if validation_errors:
        detail = "; ".join(validation_errors[:5])
        if len(validation_errors) > 5:
            detail += f" (+{len(validation_errors) - 5} more)"
        msg = f"Invalid governance policy at {policy_dir}: {detail}"
        raise ConfigurationError(msg)
    try:
        catalog = YamlGovernancePolicyLoader(policy_dir).load()
    except GovernancePolicyError as exc:
        raise ConfigurationError(str(exc)) from exc
    enforcer = SqlGovernanceEnforcer(
        catalog,
        database_kind=resolved.database_kind,
    )
    logger.info(
        "governance_configured",
        enabled=True,
        path=str(policy_dir),
        catalog_enabled=catalog.enabled,
        role_count=len(catalog.roles),
    )
    return GovernanceComponents(enforcer=enforcer, enabled=True)
