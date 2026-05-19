"""Unit tests for database engine factory."""

from __future__ import annotations

from sqlalchemy import text

from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.database.engine_factory import DatabaseConnectionFactory


def _settings_without_dotenv(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type,call-arg]


def test_connection_config_from_sqlite_url() -> None:
    settings = _settings_without_dotenv(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
    )
    factory = DatabaseConnectionFactory(settings)
    config = factory.connection_config_from_settings(readonly=True)
    assert config.kind == DatabaseKind.SQLITE
    assert config.readonly is True


def test_create_sqlite_engine_and_query() -> None:
    settings = _settings_without_dotenv(
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
    )
    factory = DatabaseConnectionFactory(settings)
    config = factory.connection_config_from_settings()
    engine = factory.create_engine(config)
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()
    assert value == 1


def test_build_url_mssql_from_components() -> None:
    settings = _settings_without_dotenv(
        database_kind=DatabaseKind.MSSQL,
        db_readonly_user="ro",
        db_readonly_password="secret",
        db_host="mssql.local",
        db_port=1433,
        db_name="campus_analytics",
    )
    factory = DatabaseConnectionFactory(settings)
    url = factory.build_url(kind="mssql", readonly=True)
    assert "mssql+pyodbc://" in url
    assert "mssql.local:1433/campus_analytics" in url
