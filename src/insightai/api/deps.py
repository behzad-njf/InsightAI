"""FastAPI dependency injection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import Request

from insightai.application.use_cases.ask import AskUseCase
from insightai.application.use_cases.classify_query_route import ClassifyQueryRouteUseCase
from insightai.application.use_cases.generate_rag_answer import GenerateRAGAnswerUseCase
from insightai.application.use_cases.hybrid_ask import HybridAskUseCase
from insightai.application.use_cases.langchain_agent_ask import LangChainAgentAskUseCase
from insightai.application.use_cases.retrieve_rag_context import RetrieveRAGContextUseCase
from insightai.domain.exceptions import ConfigurationError
from insightai.infrastructure.ai.langchain.agent_runner import LangChainAgentRunner
from insightai.infrastructure.ai.langchain.availability import langchain_available
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
    from insightai.domain.ports.cache import ICache
    from insightai.domain.ports.chat_session_store import IChatSessionStore
    from insightai.domain.ports.database import IDatabaseHealthCheck
    from insightai.domain.ports.schema_repository import ISchemaRepository


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


def get_schema_repository_dep(request: Request) -> ISchemaRepository:
    schema = getattr(request.app.state, "schema", None)
    if schema is not None:
        return cast("ISchemaRepository", schema.repository)
    return get_schema_repository()


def get_schema_context_use_case(request: Request) -> BuildSchemaContextUseCase:
    schema = getattr(request.app.state, "schema", None)
    return BuildSchemaContextUseCase(
        get_schema_repository_dep(request),
        cache=get_cache(request),
        settings=get_settings(request),
        schema_path=schema.schema_path if schema is not None else None,
    )


def get_generate_sql_use_case(request: Request) -> GenerateSQLUseCase:
    ai: AIComponents = request.app.state.ai
    retrieve_rag = None
    settings = ai.settings
    rag = getattr(request.app.state, "rag", None)
    if (
        rag is not None
        and rag.enabled
        and rag.embedding_provider is not None
        and rag.vector_store is not None
        and settings.sql_knowledge_context_enabled
    ):
        retrieve_rag = RetrieveRAGContextUseCase(
            rag.embedding_provider,
            rag.vector_store,
            settings,
        )
    semantic = getattr(request.app.state, "semantic", None)
    match_trusted = (
        semantic.match_use_case
        if semantic is not None and semantic.enabled
        else None
    )
    return GenerateSQLUseCase(
        get_schema_context_use_case(request),
        ai.sql_generator,
        ai.settings,
        retrieve_rag=retrieve_rag,
        match_trusted=match_trusted,
    )


def get_ask_use_case(
    request: Request,
) -> AskUseCase | HybridAskUseCase | LangChainAgentAskUseCase:
    """Full NL pipeline; hybrid RAG or LangChain agent when configured."""
    settings = get_settings(request)
    governance = getattr(request.app.state, "governance", None)
    enforcer = governance.enforcer if governance is not None else None
    db: DatabaseComponents | None = request.app.state.database
    sql_ask = AskUseCase(
        get_generate_sql_use_case(request),
        get_run_query_use_case(request),
        get_generate_answer_use_case(request),
        settings,
        request.app.state.audit,
        governance=enforcer,
        sql_validator=db.validator if db is not None else None,
    )
    rag = getattr(request.app.state, "rag", None)
    if rag is None or not rag.enabled:
        return sql_ask
    if (
        rag.embedding_provider is None
        or rag.vector_store is None
        or rag.query_router is None
        or rag.rag_answer_generator is None
    ):
        return sql_ask

    retrieve_rag = RetrieveRAGContextUseCase(
        rag.embedding_provider,
        rag.vector_store,
        settings,
    )

    if settings.langchain_agent_enabled:
        if not langchain_available():
            raise ConfigurationError(
                "INSIGHTAI_LANGCHAIN_AGENT_ENABLED requires LangChain. "
                "Install with: pip install 'insightai[langchain]'",
            )
        agent_runner = LangChainAgentRunner(
            retrieve_rag,
            get_generate_sql_use_case(request),
            get_run_query_use_case(request),
            settings,
        )
        return LangChainAgentAskUseCase(
            agent_runner,
            get_generate_answer_use_case(request),
            settings=settings,
            audit=request.app.state.audit,
        )

    return HybridAskUseCase(
        sql_ask,
        ClassifyQueryRouteUseCase(rag.query_router),
        retrieve_rag,
        GenerateRAGAnswerUseCase(rag.rag_answer_generator),
        get_generate_answer_use_case(request),
        settings=settings,
        audit=request.app.state.audit,
    )


def get_generate_answer_use_case(request: Request) -> GenerateAnswerUseCase:
    ai: AIComponents = request.app.state.ai
    return GenerateAnswerUseCase(ai.answer_generator, ai.settings)


def get_cache(request: Request) -> ICache:
    """Application cache (no-op when ``INSIGHTAI_CACHE_ENABLED=false``)."""
    return cast("ICache", request.app.state.cache.cache)


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
        cache=get_cache(request),
    )
