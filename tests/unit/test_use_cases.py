"""Unit tests for application use cases."""

from __future__ import annotations

from unittest.mock import MagicMock

from insightai.application.use_cases.health_check import HealthCheckUseCase
from insightai.application.use_cases.readiness_check import ReadinessCheckUseCase
from insightai.domain.models.database import DatabaseHealthStatus, DatabaseKind


def test_health_check_use_case() -> None:
    result = HealthCheckUseCase().execute()
    assert result.status == "ok"
    assert result.version


def test_readiness_without_database() -> None:
    result = ReadinessCheckUseCase(None).execute()
    assert result.status == "ready"
    assert result.database is None


def test_readiness_degraded_when_db_unhealthy() -> None:
    health = MagicMock()
    health.check.return_value = DatabaseHealthStatus(
        healthy=False,
        kind=DatabaseKind.POSTGRESQL,
        message="connection refused",
    )
    result = ReadinessCheckUseCase(health).execute()
    assert result.status == "degraded"
    assert result.database is not None
    assert result.database.healthy is False
