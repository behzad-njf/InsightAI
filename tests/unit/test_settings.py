"""Unit tests for application settings."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

import pytest

from insightai.domain.exceptions import ConfigurationError
from insightai.infrastructure.config.settings import (
    AppEnvironment,
    Settings,
    clear_settings_cache,
    get_settings,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings_without_dotenv(**overrides: object) -> Settings:
    """Build settings ignoring the repo .env file (isolated unit tests)."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type,call-arg]


def test_settings_loads_groq_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
    monkeypatch.setenv("INSIGHTAI_LLM_PROVIDER", "groq")
    settings = _settings_without_dotenv()
    assert settings.require_groq_api_key() == "gsk-test-key"


def test_settings_grok_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROK_API_KEY", "gsk-from-grok-alias")
    settings = _settings_without_dotenv()
    assert settings.require_groq_api_key() == "gsk-from-grok-alias"


def test_chat_streaming_enabled_defaults_true() -> None:
    settings = _settings_without_dotenv()
    assert settings.chat_streaming_enabled is True


def test_chat_streaming_can_be_disabled() -> None:
    settings = _settings_without_dotenv(chat_streaming_enabled=False)
    assert settings.chat_streaming_enabled is False


def test_settings_missing_groq_key_raises() -> None:
    settings = _settings_without_dotenv(groq_api_key=None)
    with pytest.raises(ConfigurationError):
        settings.require_groq_api_key()


def test_resolve_prefers_db_components_when_password_set() -> None:
    """DB_* wins over a broken explicit URL (e.g. ``&`` in sa password)."""
    password = "p@ss#word&more"  # fake — special chars for URL-encoding tests only
    settings = _settings_without_dotenv(
        database_kind="mssql",
        database_readonly_url=(
            f"mssql+pyodbc://sa:{password}@localhost:1433/campus_analytics"
            "?driver=ODBC+Driver+17+for+SQL+Server"
        ),
        db_readonly_user="sa",
        db_readonly_password=password,
        db_host="localhost",
        db_port=1433,
        db_name="campus_analytics",
    )
    url = settings.resolve_database_url(readonly=True)
    assert quote_plus(password) in url
    assert "TrustServerCertificate=yes" in url


def test_resolve_mssql_readonly_url_from_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTAI_DATABASE_KIND", "mssql")
    monkeypatch.setenv("DB_READONLY_USER", "readonly_user")
    monkeypatch.setenv("DB_READONLY_PASSWORD", "secret")
    monkeypatch.setenv("DB_HOST", "sqlserver.local")
    monkeypatch.setenv("DB_PORT", "1433")
    monkeypatch.setenv("DB_NAME", "campus_analytics")
    settings = _settings_without_dotenv(database_kind="mssql")
    url = settings.resolve_database_url(readonly=True)
    assert url.startswith("mssql+pyodbc://readonly_user:")
    assert "sqlserver.local:1433/campus_analytics" in url


def test_model_dump_safe_redacts_secrets() -> None:
    settings = _settings_without_dotenv(groq_api_key="gsk-secret")
    safe = settings.model_dump_safe()
    assert safe["groq_api_key"] == "***REDACTED***"


def test_schema_path_resolves_relative_to_project_root() -> None:
    settings = _settings_without_dotenv(
        schema_markdown_path=Path("schema/database_schema.md"),
    )
    path = settings.schema_markdown_absolute
    assert path.name == "database_schema.md"
    assert path.parent.name == "schema"


def test_sql_query_timeout_default() -> None:
    settings = _settings_without_dotenv()
    assert settings.sql_query_timeout_seconds == 120
    assert settings.get_query_execution_options().timeout_seconds == 120


def test_answer_max_prompt_rows_default() -> None:
    settings = _settings_without_dotenv()
    assert settings.answer_max_prompt_rows == 50


def test_answer_max_prompt_rows_from_env() -> None:
    settings = _settings_without_dotenv(answer_max_prompt_rows=25)
    assert settings.answer_max_prompt_rows == 25


def test_get_query_execution_options_from_env_fields() -> None:
    settings = _settings_without_dotenv(
        sql_max_rows=250,
        sql_query_timeout_seconds=12,
        sql_enforce_readonly=True,
    )
    opts = settings.get_query_execution_options()
    assert opts.max_rows == 250
    assert opts.timeout_seconds == 12
    assert opts.enforce_readonly is True


def test_production_rejects_debug() -> None:
    with pytest.raises(ValueError):
        _settings_without_dotenv(env=AppEnvironment.PRODUCTION, debug=True)


def test_parsed_cors_allow_origins_splits_comma_list() -> None:
    settings = _settings_without_dotenv(
        cors_allow_origins="http://127.0.0.1:8765, https://app.example.com",
    )
    assert settings.parsed_cors_allow_origins() == [
        "http://127.0.0.1:8765",
        "https://app.example.com",
    ]


def test_parsed_cors_allow_origins_empty_when_unset() -> None:
    settings = _settings_without_dotenv()
    assert settings.parsed_cors_allow_origins() == []


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTAI_LOG_LEVEL", "WARNING")
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.log_level == "WARNING"
