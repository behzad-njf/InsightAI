"""Application settings loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from insightai.domain.exceptions import ConfigurationError
from insightai.domain.models.auth import ApiAuthMode
from insightai.domain.models.database import DatabaseKind, QueryExecutionOptions
from insightai.domain.models.llm import AIFrameworkKind, LLMProviderKind
from insightai.infrastructure.config.database_url import (
    mssql_url_with_trust_server_certificate,
    normalize_sqlalchemy_url,
)


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """Central configuration — all env access should go through this class."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="INSIGHTAI_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- Application ---
    env: AppEnvironment = AppEnvironment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    # --- LLM ---
    llm_provider: LLMProviderKind = LLMProviderKind.GROQ
    llm_max_tokens: int = Field(default=4096, ge=1)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    groq_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GROQ_API_KEY",
            "GROK_API_KEY",
            "INSIGHTAI_GROQ_API_KEY",
        ),
    )
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: int = Field(default=60, ge=1)
    groq_max_retries: int = Field(default=2, ge=0)

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "INSIGHTAI_OPENAI_API_KEY"),
    )
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: int = Field(default=60, ge=1)
    openai_max_retries: int = Field(default=2, ge=0)

    # --- AI framework ---
    ai_framework: AIFrameworkKind = AIFrameworkKind.LLAMAINDEX

    # --- Database ---
    database_kind: DatabaseKind = DatabaseKind.MSSQL
    database_url: str | None = None
    database_readonly_url: str | None = None

    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=1433, validation_alias="DB_PORT")
    db_name: str = Field(default="campus_analytics", validation_alias="DB_NAME")
    db_user: str | None = Field(default=None, validation_alias="DB_USER")
    db_password: str | None = Field(default=None, validation_alias="DB_PASSWORD")
    db_readonly_user: str | None = Field(default=None, validation_alias="DB_READONLY_USER")
    db_readonly_password: str | None = Field(
        default=None,
        validation_alias="DB_READONLY_PASSWORD",
    )
    db_odbc_driver: str = Field(
        default="ODBC Driver 17 for SQL Server",
        validation_alias="DB_ODBC_DRIVER",
    )

    # --- SQL safety ---
    sql_max_rows: int = Field(default=1000, ge=1, le=100_000)
    sql_query_timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=600,
        description="Per-query timeout for read-only execution (ODBC/pyodbc on MSSQL).",
    )
    sql_enforce_readonly: bool = True

    # --- Chat API (Phase 7) ---
    chat_max_question_length: int = Field(
        default=4000,
        ge=1,
        le=50_000,
        description="Maximum characters allowed in POST /api/v1/chat question body.",
    )
    chat_session_store: str = Field(
        default="memory",
        description="Session backend: memory | redis (redis requires optional redis package).",
    )
    chat_session_ttl_seconds: int = Field(
        default=604_800,
        ge=60,
        le=2_592_000,
        description="Session and message TTL (default 7 days).",
    )
    chat_session_max_messages: int = Field(
        default=200,
        ge=2,
        le=10_000,
        description="Max messages per session (user and assistant messages count separately).",
    )
    chat_session_list_default_limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Default page size for GET /chat/sessions/{id}/messages.",
    )
    chat_streaming_enabled: bool = Field(
        default=True,
        description="Enable POST /api/v1/chat/stream (SSE). When false, returns HTTP 404.",
    )

    # --- Observability (Phase 8) ---
    observability_audit_enabled: bool = Field(
        default=True,
        description="Emit ask_audit_* structured events for /chat and /ask pipelines.",
    )
    observability_log_sql: bool = Field(
        default=False,
        description="Include executed SQL in audit events (off by default — PII risk).",
    )
    observability_log_question: bool = Field(
        default=False,
        description="Include raw question text in audit events (off by default — PII risk).",
    )
    observability_llm_usage_enabled: bool = Field(
        default=True,
        description="Emit llm_usage audit event after each LLM provider call.",
    )
    observability_tracing_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry traces (requires pip install insightai[otel]).",
    )
    observability_otlp_endpoint: str | None = Field(
        default=None,
        description="OTLP HTTP traces endpoint (e.g. http://localhost:4318/v1/traces).",
    )
    observability_service_name: str = Field(
        default="insightai",
        description="OpenTelemetry service.name resource attribute.",
    )
    observability_service_version: str = Field(
        default="0.1.0",
        description="OpenTelemetry service.version resource attribute.",
    )
    observability_metrics_enabled: bool = Field(
        default=False,
        description="Expose GET /metrics for Prometheus (pip install insightai[prometheus]).",
    )

    # --- API authentication (Phase 7.4) ---
    api_auth_mode: ApiAuthMode = Field(
        default=ApiAuthMode.NONE,
        description="Inbound API auth: none | api_key | jwt (required in production).",
    )
    api_keys: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INSIGHTAI_API_KEYS", "INSIGHTAI_API_KEY"),
        description="Comma-separated API keys when api_auth_mode=api_key.",
    )
    jwt_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INSIGHTAI_JWT_SECRET", "JWT_SECRET"),
        description="HS* signing secret when api_auth_mode=jwt.",
    )
    jwt_algorithm: str = Field(default="HS256", min_length=3, max_length=16)
    jwt_audience: str | None = None
    jwt_issuer: str | None = None

    # --- Rate limiting (Phase 7.5) ---
    rate_limit_enabled: bool = Field(
        default=False,
        description="Enable sliding-window limits on protected /api/v1 routes.",
    )
    rate_limit_requests: int = Field(
        default=60,
        ge=1,
        le=100_000,
        description="Max requests per window per client (IP or authenticated principal).",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=86_400,
        description="Sliding window size in seconds.",
    )
    rate_limit_store: str = Field(
        default="memory",
        description="Backend: memory | redis (redis requires optional redis package).",
    )
    rate_limit_trust_forwarded_for: bool = Field(
        default=False,
        description="Use first X-Forwarded-For address when resolving client IP.",
    )

    # --- Answer generation (Phase 6) ---
    answer_max_prompt_rows: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max result rows embedded in answer-generation LLM prompts.",
    )

    # --- Redis (Phase 9) ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Schema ---
    schema_markdown_path: Path = Path("schema/database_schema.md")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("schema_markdown_path", mode="before")
    @classmethod
    def coerce_schema_path(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("api_auth_mode", mode="before")
    @classmethod
    def coerce_api_auth_mode(cls, value: object) -> ApiAuthMode:
        if isinstance(value, ApiAuthMode):
            return value
        if isinstance(value, str):
            return ApiAuthMode(value.strip().lower())
        msg = f"Invalid api_auth_mode: {value!r}"
        raise ValueError(msg)

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.env == AppEnvironment.PRODUCTION and self.debug:
            msg = "INSIGHTAI_DEBUG must be false in production."
            raise ValueError(msg)
        if self.env == AppEnvironment.PRODUCTION and self.api_auth_mode == ApiAuthMode.NONE:
            msg = "INSIGHTAI_API_AUTH_MODE must be 'api_key' or 'jwt' in production (not 'none')."
            raise ValueError(msg)
        if self.api_auth_mode == ApiAuthMode.API_KEY and not self.parsed_api_keys():
            msg = "INSIGHTAI_API_KEYS is required when INSIGHTAI_API_AUTH_MODE=api_key."
            raise ValueError(msg)
        if self.api_auth_mode == ApiAuthMode.JWT and (
            not self.jwt_secret or not self.jwt_secret.strip()
        ):
            msg = "INSIGHTAI_JWT_SECRET is required when INSIGHTAI_API_AUTH_MODE=jwt."
            raise ValueError(msg)
        if self.env == AppEnvironment.PRODUCTION and not self.rate_limit_enabled:
            msg = "INSIGHTAI_RATE_LIMIT_ENABLED must be true in production."
            raise ValueError(msg)
        return self

    def parsed_api_keys(self) -> frozenset[str]:
        """Configured API keys (comma-separated in ``INSIGHTAI_API_KEYS``)."""
        if not self.api_keys or not self.api_keys.strip():
            return frozenset()
        return frozenset(part.strip() for part in self.api_keys.split(",") if part.strip())

    def require_jwt_secret(self) -> str:
        if not self.jwt_secret or not self.jwt_secret.strip():
            msg = "Missing JWT secret. Set INSIGHTAI_JWT_SECRET."
            raise ConfigurationError(msg)
        return self.jwt_secret.strip()

    @property
    def is_production(self) -> bool:
        return self.env == AppEnvironment.PRODUCTION

    @property
    def project_root(self) -> Path:
        """Repository root (parent of src/ when running from package)."""
        return Path(__file__).resolve().parents[4]

    @property
    def schema_markdown_absolute(self) -> Path:
        path = self.schema_markdown_path
        if path.is_absolute():
            return path
        return self.project_root / path

    def get_active_llm_api_key(self) -> str:
        if self.llm_provider == LLMProviderKind.GROQ:
            return self.require_groq_api_key()
        if self.llm_provider == LLMProviderKind.OPENAI:
            return self.require_openai_api_key()
        msg = f"Unsupported LLM provider: {self.llm_provider}"
        raise ConfigurationError(msg)

    def get_active_llm_model(self) -> str:
        if self.llm_provider == LLMProviderKind.GROQ:
            return self.groq_model
        return self.openai_model

    def require_groq_api_key(self) -> str:
        if not self.groq_api_key or not self.groq_api_key.strip():
            msg = "Missing Groq API key. Set GROQ_API_KEY or GROK_API_KEY in .env."
            raise ConfigurationError(msg)
        return self.groq_api_key.strip()

    def require_openai_api_key(self) -> str:
        if not self.openai_api_key or not self.openai_api_key.strip():
            msg = "Missing OpenAI API key. Set OPENAI_API_KEY in .env."
            raise ConfigurationError(msg)
        return self.openai_api_key.strip()

    def get_query_execution_options(self) -> QueryExecutionOptions:
        return QueryExecutionOptions(
            max_rows=self.sql_max_rows,
            timeout_seconds=self.sql_query_timeout_seconds,
            enforce_readonly=self.sql_enforce_readonly,
        )

    def resolve_database_url(
        self,
        *,
        readonly: bool = True,
        kind: DatabaseKind | None = None,
    ) -> str:
        """
        Return SQLAlchemy URL for the requested connection mode.

        Priority:
        1. DB_* components when a password is set (avoids broken manual URLs).
        2. INSIGHTAI_DATABASE_READONLY_URL / INSIGHTAI_DATABASE_URL
           (normalized; TrustServerCertificate for MSSQL).
        3. DB_* components without password (user only).
        """
        explicit = self.database_readonly_url if readonly else self.database_url
        password = self.db_readonly_password if readonly else self.db_password

        built = self._build_url_from_components(readonly=readonly, kind=kind)
        if built and password:
            return built

        if explicit and explicit.strip():
            url = normalize_sqlalchemy_url(explicit)
            db_kind = kind or self.database_kind
            if url.lower().startswith("mssql") or db_kind == DatabaseKind.MSSQL:
                url = mssql_url_with_trust_server_certificate(url)
            return url

        if built:
            return built

        msg = (
            "Database URL not configured. Set INSIGHTAI_DATABASE_READONLY_URL "
            "or DB_HOST/DB_READONLY_USER/DB_READONLY_PASSWORD (and related vars)."
        )
        raise ConfigurationError(msg)

    def _build_url_from_components(
        self,
        *,
        readonly: bool,
        kind: DatabaseKind | None = None,
    ) -> str | None:
        user = self.db_readonly_user if readonly else self.db_user
        password = self.db_readonly_password if readonly else self.db_password
        if not user:
            return None

        safe_user = quote_plus(user)
        safe_password = quote_plus(password or "")
        db_kind = kind or self.database_kind

        if db_kind == DatabaseKind.MSSQL:
            driver = quote_plus(self.db_odbc_driver)
            url = (
                f"mssql+pyodbc://{safe_user}:{safe_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
                f"?driver={driver}&TrustServerCertificate=yes"
            )
            return url
        if db_kind == DatabaseKind.POSTGRESQL:
            return (
                f"postgresql+psycopg2://{safe_user}:{safe_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        if db_kind == DatabaseKind.SQLITE:
            db_path = self.db_name if self.db_name.endswith(".db") else f"{self.db_name}.db"
            return f"sqlite:///{db_path}"

        return None

    def model_dump_safe(self) -> dict[str, Any]:
        """Settings snapshot with secrets redacted (for logs/debug)."""
        data = self.model_dump()
        secret_fields = (
            "groq_api_key",
            "openai_api_key",
            "api_keys",
            "jwt_secret",
            "db_password",
            "db_readonly_password",
            "database_url",
            "database_readonly_url",
        )
        for key in secret_fields:
            if getattr(self, key, None):
                data[key] = "***REDACTED***"
        return data


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call `clear_settings_cache()` in tests."""
    return Settings()


def clear_settings_cache() -> None:
    """Reset cached settings (use in tests after env changes)."""
    get_settings.cache_clear()
