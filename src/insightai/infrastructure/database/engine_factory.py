"""SQLAlchemy engine factory — multi-dialect connection management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

from insightai.domain.exceptions import ConfigurationError, DatabaseConfigurationError
from insightai.domain.models.database import DatabaseConnectionConfig, DatabaseKind
from insightai.domain.ports.database import IDatabaseConnectionFactory
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.database.dialect import infer_kind_from_url


class DatabaseConnectionFactory(IDatabaseConnectionFactory):
    """Creates SQLAlchemy engines from domain config or application settings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def build_url(self, *, kind: str, readonly: bool = True) -> str:
        try:
            db_kind = DatabaseKind(kind.lower())
        except ValueError as exc:
            msg = f"Unsupported database kind: {kind}"
            raise DatabaseConfigurationError(msg) from exc

        return self._settings.resolve_database_url(readonly=readonly, kind=db_kind)

    def connection_config_from_settings(
        self,
        *,
        readonly: bool = True,
    ) -> DatabaseConnectionConfig:
        url = self._settings.resolve_database_url(readonly=readonly)
        return self.connection_config_from_url(url, readonly=readonly)

    def connection_config_from_url(
        self,
        url: str,
        *,
        readonly: bool = False,
    ) -> DatabaseConnectionConfig:
        from insightai.infrastructure.config.database_url import normalize_sqlalchemy_url

        normalized = normalize_sqlalchemy_url(url.strip())
        kind = infer_kind_from_url(normalized) or self._settings.database_kind
        return DatabaseConnectionConfig(
            kind=kind,
            url=normalized,
            readonly=readonly,
            echo_sql=self._settings.debug,
        )

    def create_engine(self, config: DatabaseConnectionConfig) -> Engine:
        self._ensure_driver_available(config.kind)
        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "echo": config.echo_sql,
        }

        if config.kind == DatabaseKind.SQLITE:
            if ":memory:" in config.url:
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                engine_kwargs["poolclass"] = StaticPool
        elif config.kind == DatabaseKind.MSSQL:
            engine_kwargs["pool_size"] = config.pool_size
            engine_kwargs["pool_timeout"] = config.pool_timeout_seconds
            # pyodbc command timeout (seconds); aligns with executor execution_options.
            engine_kwargs["connect_args"] = {
                "timeout": self._settings.sql_query_timeout_seconds,
            }
        else:
            engine_kwargs["pool_size"] = config.pool_size
            engine_kwargs["pool_timeout"] = config.pool_timeout_seconds

        return create_engine(config.url, **engine_kwargs)

    @staticmethod
    def _ensure_driver_available(kind: DatabaseKind) -> None:
        if kind != DatabaseKind.MSSQL:
            return
        try:
            import pyodbc  # noqa: F401
        except ImportError as exc:
            msg = "MSSQL requires pyodbc. Install with: pip install -e '.[mssql]'"
            raise ConfigurationError(msg) from exc
