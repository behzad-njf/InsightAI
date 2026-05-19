"""Readiness health check use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightai import __version__

if TYPE_CHECKING:
    from insightai.domain.models.database import DatabaseHealthStatus
    from insightai.domain.ports.database import IDatabaseHealthCheck


@dataclass(frozen=True)
class ReadinessCheckResult:
    status: str
    version: str
    database: DatabaseHealthStatus | None


class ReadinessCheckUseCase:
    """
    Readiness probe — includes database when configured.

    ``status`` is ``ready`` when DB is healthy or not configured; ``degraded`` otherwise.
    """

    def __init__(self, database_health: IDatabaseHealthCheck | None) -> None:
        self._database_health = database_health

    def execute(self) -> ReadinessCheckResult:
        if self._database_health is None:
            return ReadinessCheckResult(
                status="ready",
                version=__version__,
                database=None,
            )

        db_status = self._database_health.check()
        overall = "ready" if db_status.healthy else "degraded"
        return ReadinessCheckResult(
            status=overall,
            version=__version__,
            database=db_status,
        )
