"""Liveness health check use case."""

from __future__ import annotations

from dataclasses import dataclass

from insightai import __version__


@dataclass(frozen=True)
class HealthCheckResult:
    status: str
    version: str


class HealthCheckUseCase:
    """Returns service liveness without external dependencies."""

    def execute(self) -> HealthCheckResult:
        return HealthCheckResult(status="ok", version=__version__)
