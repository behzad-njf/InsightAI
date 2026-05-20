"""Domain exceptions — infrastructure maps these to HTTP/status codes."""

from __future__ import annotations


class InsightAIError(Exception):
    """Base exception for all InsightAI domain errors."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class ConfigurationError(InsightAIError):
    """Invalid or missing application configuration."""


class PromptError(InsightAIError):
    """Prompt template loading or rendering errors (Phase 3+)."""


class PromptNotFoundError(PromptError):
    """A required prompt file was not found."""


class SchemaError(InsightAIError):
    """Schema document or metadata errors (Phase 2+)."""


class SchemaNotFoundError(SchemaError):
    """Requested schema resource was not found."""


class LLMError(InsightAIError):
    """Base class for LLM-related failures."""


class LLMProviderError(LLMError):
    """LLM provider returned an error or invalid response."""


class LLMProviderUnavailableError(LLMProviderError):
    """LLM provider is unreachable or rate-limited after retries."""


class LLMConfigurationError(LLMError):
    """LLM provider configuration is invalid (missing key, model, etc.)."""


class EmbeddingError(InsightAIError):
    """Base class for embedding provider failures (Phase 10)."""


class EmbeddingProviderError(EmbeddingError):
    """Embedding provider returned an error or invalid response."""


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Embedding provider is unreachable or rate-limited after retries."""


class EmbeddingConfigurationError(EmbeddingError):
    """Embedding provider configuration is invalid (missing key, model, etc.)."""


class VectorStoreError(InsightAIError):
    """Vector store / pgvector failures (Phase 10)."""


class VectorStoreConfigurationError(VectorStoreError):
    """Vector store is not configured or pgvector is unavailable."""


class AIFrameworkError(InsightAIError):
    """AI framework adapter failure (LlamaIndex, LangChain, etc.)."""


class AIFrameworkNotSupportedError(AIFrameworkError):
    """Requested framework is not implemented yet (e.g. LangChain stub)."""


class DatabaseError(InsightAIError):
    """Base class for database-related failures."""


class DatabaseConnectionError(DatabaseError):
    """Failed to connect or ping the database."""

    def __init__(
        self,
        message: str,
        *,
        driver_message: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code or "DATABASE_CONNECTION_ERROR")
        self.driver_message = driver_message


class DatabaseConfigurationError(DatabaseError):
    """Database URL or dialect configuration is invalid."""


class DatabaseQueryError(DatabaseError):
    """Query execution failed at the database layer."""


class DatabaseQueryTimeoutError(DatabaseQueryError):
    """Query exceeded the configured timeout."""

    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: int | None = None,
        driver_message: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code or "DATABASE_QUERY_TIMEOUT")
        self.timeout_seconds = timeout_seconds
        self.driver_message = driver_message


class SQLGenerationError(InsightAIError):
    """SQL generation failed (LLM output, parsing, or policy)."""


class SQLGenerationParseError(SQLGenerationError):
    """LLM response was not valid JSON or did not match the expected schema."""


class AnswerGenerationError(InsightAIError):
    """Answer generation failed (LLM output or parsing)."""


class AnswerGenerationParseError(AnswerGenerationError):
    """LLM response was not valid JSON or did not match the expected schema."""


class SQLGenerationRejectedError(SQLGenerationError):
    """Generated SQL failed post-processing or read-only policy checks."""

    def __init__(
        self,
        message: str,
        *,
        sql: str | None = None,
        violations: list[str] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code or "SQL_GENERATION_REJECTED")
        self.sql = sql
        self.violations = list(violations or [])


class SQLError(InsightAIError):
    """Base class for SQL validation and safety errors."""


class SQLValidationError(SQLError):
    """SQL failed structural or policy validation."""

    def __init__(
        self,
        message: str,
        *,
        sql: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.sql = sql
        self.reason = reason or message


class AuthenticationError(InsightAIError):
    """API authentication failed or credentials are missing."""


class RateLimitExceededError(InsightAIError):
    """Client exceeded the configured request rate."""

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        *,
        retry_after_seconds: int = 60,
        limit: int | None = None,
    ) -> None:
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")
        self.retry_after_seconds = max(1, retry_after_seconds)
        self.limit = limit


class InvalidCredentialsError(AuthenticationError):
    """Missing or invalid API key / JWT."""

    def __init__(self, message: str = "Invalid or missing credentials.") -> None:
        super().__init__(message, code="UNAUTHORIZED")


class ChatSessionError(InsightAIError):
    """Chat session storage or lifecycle error."""


class ChatSessionNotFoundError(ChatSessionError):
    """Requested session id does not exist or has expired."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Chat session not found: {session_id}",
            code="CHAT_SESSION_NOT_FOUND",
        )
        self.session_id = session_id


class ChatSessionMessageLimitError(ChatSessionError):
    """Session has reached the configured message cap."""

    def __init__(self, session_id: str, *, limit: int) -> None:
        super().__init__(
            f"Chat session {session_id} exceeded the message limit ({limit}).",
            code="CHAT_SESSION_MESSAGE_LIMIT",
        )
        self.session_id = session_id
        self.limit = limit


class ReadOnlySQLViolationError(SQLValidationError):
    """SQL contains disallowed statements or keywords (write operations)."""

    def __init__(
        self,
        message: str,
        *,
        sql: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message, sql=sql, reason=reason)
        self.code = "READ_ONLY_SQL_VIOLATION"
