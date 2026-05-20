"""FastAPI dependency injection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import Request

from insightai.application.use_cases.ask import AskUseCase
from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.application.use_cases.chat_session import ChatSessionUseCase
from insightai.application.use_cases.generate_answer import GenerateAnswerUseCase
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase
from insightai.application.use_cases.health_check import HealthCheckUseCase
from insightai.application.use_cases.llm_completion import LLMCompletionUseCase
from insightai.application.use_cases.readiness_check import ReadinessCheckUseCase
from insightai.application.use_cases.run_query import RunQueryUseCase
from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.infrastructure.ai.factory import AIComponents
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.database.bootstrap import DatabaseComponents
from insightai.infrastructure.schema.loader import get_schema_repository

if TYPE_CHECKING:
    from insightai.domain.ports.chat_session_store import IChatSessionStore
    from insightai.domain.ports.database import IDatabaseHealthCheck


def get_settings(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


def get_ai_components(request: Request) -> AIComponents:
    return cast("AIComponents", request.app.state.ai)


def get_database_components(request: Request) -> DatabaseComponents | None:
    return cast("DatabaseComponents | None", request.app.state.database)


def get_health_use_case() -> HealthCheckUseCase:
    return HealthCheckUseCase()


def get_readiness_use_case(request: Request) -> ReadinessCheckUseCase:
    db: DatabaseComponents | None = request.app.state.database
    health: IDatabaseHealthCheck | None = db.health_check if db else None
    return ReadinessCheckUseCase(health)


def get_llm_completion_use_case(request: Request) -> LLMCompletionUseCase:
    ai: AIComponents = request.app.state.ai
    return LLMCompletionUseCase(ai.framework)


def get_schema_repository_dep() -> ISchemaRepository:
    return get_schema_repository()


def get_schema_context_use_case() -> BuildSchemaContextUseCase:
    return BuildSchemaContextUseCase(get_schema_repository())


def get_generate_sql_use_case(request: Request) -> GenerateSQLUseCase:
    ai: AIComponents = request.app.state.ai
    return GenerateSQLUseCase(
        BuildSchemaContextUseCase(get_schema_repository()),
        ai.sql_generator,
        ai.settings,
    )


def get_ask_use_case(request: Request) -> AskUseCase:
    """Full NL → SQL → execute → answer pipeline (requires configured database)."""
    return AskUseCase(
        get_generate_sql_use_case(request),
        get_run_query_use_case(request),
        get_generate_answer_use_case(request),
        get_settings(request),
        request.app.state.audit,
    )


def get_generate_answer_use_case(request: Request) -> GenerateAnswerUseCase:
    ai: AIComponents = request.app.state.ai
    return GenerateAnswerUseCase(ai.answer_generator, ai.settings)


def get_chat_session_store(request: Request) -> IChatSessionStore:
    return cast("IChatSessionStore", request.app.state.chat_sessions.store)


def get_chat_session_use_case(request: Request) -> ChatSessionUseCase:
    return ChatSessionUseCase(
        get_chat_session_store(request),
        get_settings(request),
    )


def get_run_query_use_case(request: Request) -> RunQueryUseCase:
    db: DatabaseComponents | None = request.app.state.database
    if db is None:
        from insightai.domain.exceptions import ConfigurationError

        raise ConfigurationError(
            "Database is not configured. Set INSIGHTAI_DATABASE_READONLY_URL.",
        )
    settings = get_settings(request)
    return RunQueryUseCase(
        db.executor,
        settings,
        sql_validator=db.validator,
        execution_defaults=db.execution_options,
    )
