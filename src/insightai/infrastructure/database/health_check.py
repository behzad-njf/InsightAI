"""Database connectivity health checks."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from insightai.domain.models.database import DatabaseHealthStatus, DatabaseKind
from insightai.domain.ports.database import IDatabaseHealthCheck
from insightai.infrastructure.database.dialect import ping_sql
from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = get_logger(__name__)


class DatabaseHealthCheck(IDatabaseHealthCheck):
    """Pings the database with a dialect-appropriate SELECT."""

    def __init__(self, engine: Engine, kind: DatabaseKind) -> None:
        self._engine = engine
        self._kind = kind

    def check(self) -> DatabaseHealthStatus:
        statement = ping_sql(self._kind)
        started = time.perf_counter()
        try:
            with self._engine.connect() as connection:
                connection.execute(text(statement))
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info("database_health_ok", latency_ms=round(latency_ms, 2))
            return DatabaseHealthStatus(
                healthy=True,
                kind=self._kind,
                latency_ms=round(latency_ms, 2),
            )
        except SQLAlchemyError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.warning("database_health_failed", error=str(exc))
            return DatabaseHealthStatus(
                healthy=False,
                kind=self._kind,
                latency_ms=round(latency_ms, 2),
                message=str(exc),
            )
