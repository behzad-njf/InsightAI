"""Map domain exceptions to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from insightai.domain.exceptions import (
    AIFrameworkNotSupportedError,
    AnswerGenerationParseError,
    ChatSessionMessageLimitError,
    ChatSessionNotFoundError,
    ConfigurationError,
    InvalidCredentialsError,
    RateLimitExceededError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseQueryTimeoutError,
    InsightAIError,
    LLMProviderError,
    LLMProviderUnavailableError,
    ReadOnlySQLViolationError,
    SQLGenerationParseError,
    SQLGenerationRejectedError,
    SQLValidationError,
)
from insightai.infrastructure.logging.setup import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers for domain errors."""

    @app.exception_handler(ReadOnlySQLViolationError)
    async def readonly_sql_handler(
        _request: Request,
        exc: ReadOnlySQLViolationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": exc.code, "message": exc.message, "reason": exc.reason},
        )

    @app.exception_handler(SQLValidationError)
    async def sql_validation_handler(
        _request: Request,
        exc: SQLValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(SQLGenerationRejectedError)
    async def sql_generation_rejected_handler(
        _request: Request,
        exc: SQLGenerationRejectedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.code,
                "message": exc.message,
                "violations": exc.violations,
                "sql": exc.sql,
            },
        )

    @app.exception_handler(SQLGenerationParseError)
    async def sql_generation_parse_handler(
        _request: Request,
        exc: SQLGenerationParseError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(AnswerGenerationParseError)
    async def answer_generation_parse_handler(
        _request: Request,
        exc: AnswerGenerationParseError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(
        _request: Request,
        exc: RateLimitExceededError,
    ) -> JSONResponse:
        content: dict[str, str | int] = {
            "error": exc.code,
            "message": exc.message,
            "retry_after_seconds": exc.retry_after_seconds,
        }
        if exc.limit is not None:
            content["limit"] = exc.limit
        return JSONResponse(
            status_code=429,
            content=content,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(
        _request: Request,
        exc: InvalidCredentialsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": exc.code, "message": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(ChatSessionNotFoundError)
    async def chat_session_not_found_handler(
        _request: Request,
        exc: ChatSessionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": exc.code,
                "message": exc.message,
                "session_id": exc.session_id,
            },
        )

    @app.exception_handler(ChatSessionMessageLimitError)
    async def chat_session_message_limit_handler(
        _request: Request,
        exc: ChatSessionMessageLimitError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": exc.code,
                "message": exc.message,
                "session_id": exc.session_id,
                "limit": exc.limit,
            },
        )

    @app.exception_handler(ConfigurationError)
    async def configuration_handler(
        _request: Request,
        exc: ConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(LLMProviderUnavailableError)
    async def llm_unavailable_handler(
        _request: Request,
        exc: LLMProviderUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(LLMProviderError)
    async def llm_provider_handler(
        _request: Request,
        exc: LLMProviderError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(AIFrameworkNotSupportedError)
    async def framework_handler(
        _request: Request,
        exc: AIFrameworkNotSupportedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(DatabaseConnectionError)
    async def db_connection_handler(
        _request: Request,
        exc: DatabaseConnectionError,
    ) -> JSONResponse:
        content: dict[str, str | int | None] = {
            "error": exc.code,
            "message": exc.message,
        }
        if exc.driver_message:
            content["driver_message"] = exc.driver_message
        return JSONResponse(status_code=503, content=content)

    @app.exception_handler(DatabaseQueryTimeoutError)
    async def db_query_timeout_handler(
        _request: Request,
        exc: DatabaseQueryTimeoutError,
    ) -> JSONResponse:
        content: dict[str, str | int | None] = {
            "error": exc.code,
            "message": exc.message,
        }
        if exc.timeout_seconds is not None:
            content["timeout_seconds"] = exc.timeout_seconds
        if exc.driver_message:
            content["driver_message"] = exc.driver_message
        return JSONResponse(status_code=504, content=content)

    @app.exception_handler(DatabaseQueryError)
    async def db_query_handler(
        _request: Request,
        exc: DatabaseQueryError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(InsightAIError)
    async def insightai_handler(
        _request: Request,
        exc: InsightAIError,
    ) -> JSONResponse:
        logger.exception("unhandled_domain_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=500,
            content={"error": exc.code, "message": exc.message},
        )
