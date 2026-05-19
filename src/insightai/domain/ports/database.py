"""Database ports — connection management and read-only query execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.domain.models.database import (
        DatabaseConnectionConfig,
        DatabaseHealthStatus,
        QueryExecutionOptions,
        QueryResult,
    )


class IDatabaseConnectionFactory(ABC):
    """Creates SQLAlchemy engines for a given dialect (Step 5)."""

    @abstractmethod
    def create_engine(self, config: DatabaseConnectionConfig) -> Engine:
        """Build a SQLAlchemy Engine from domain config."""

    @abstractmethod
    def build_url(
        self,
        *,
        kind: str,
        readonly: bool = True,
    ) -> str:
        """Resolve SQLAlchemy URL from settings / env building blocks."""


class IDatabaseHealthCheck(ABC):
    """Connectivity probe for readiness endpoints."""

    @abstractmethod
    def check(self) -> DatabaseHealthStatus:
        """Ping the database and return health metadata."""


class IReadOnlyQueryExecutor(ABC):
    """
    Executes validated SELECT queries only.

    Implementations must call ISQLSafetyValidator before execution.
    """

    @abstractmethod
    def execute(
        self,
        sql: str,
        *,
        options: QueryExecutionOptions | None = None,
    ) -> QueryResult:
        """
        Execute a read-only SQL statement.

        Raises:
            ReadOnlySQLViolationError: SQL failed validation.
            DatabaseQueryError: Execution failed.
            DatabaseQueryTimeoutError: Exceeded timeout.
        """
