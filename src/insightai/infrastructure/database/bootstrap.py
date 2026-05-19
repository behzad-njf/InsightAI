"""Wire database components from application settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightai.domain.models.database import (  # noqa: TC001
    DatabaseConnectionConfig,
    QueryExecutionOptions,
)
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.database.engine_factory import DatabaseConnectionFactory
from insightai.infrastructure.database.health_check import DatabaseHealthCheck
from insightai.infrastructure.database.readonly_executor import ReadOnlyQueryExecutor
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.domain.ports.database import IDatabaseHealthCheck, IReadOnlyQueryExecutor
    from insightai.domain.ports.sql_safety import ISQLSafetyValidator


@dataclass(frozen=True)
class DatabaseComponents:
    """Bundled database infrastructure for DI / FastAPI deps (Step 7)."""

    config: DatabaseConnectionConfig
    engine: Engine
    validator: ISQLSafetyValidator
    executor: IReadOnlyQueryExecutor
    health_check: IDatabaseHealthCheck
    execution_options: QueryExecutionOptions


def build_database_components(
    settings: Settings | None = None,
    *,
    readonly: bool = True,
) -> DatabaseComponents:
    """
    Create engine, validator, executor, and health check from settings.

    Uses readonly URL by default for AI query paths.
    """
    settings = settings or get_settings()
    factory = DatabaseConnectionFactory(settings)
    config = factory.connection_config_from_settings(readonly=readonly)
    engine = factory.create_engine(config)
    execution_options = settings.get_query_execution_options()
    validator = create_sql_safety_validator(settings=settings, kind=config.kind)
    executor = ReadOnlyQueryExecutor(
        engine,
        validator,
        kind=config.kind,
        default_options=execution_options,
    )
    health = DatabaseHealthCheck(engine, config.kind)
    return DatabaseComponents(
        config=config,
        engine=engine,
        validator=validator,
        executor=executor,
        health_check=health,
        execution_options=execution_options,
    )
