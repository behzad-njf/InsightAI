"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from insightai import __version__
from insightai.api.exception_handlers import register_exception_handlers
from insightai.api.metrics_middleware import MetricsMiddleware
from insightai.api.middleware import RequestIdMiddleware
from insightai.api.routes.metrics import router as metrics_router
from insightai.api.tracing_middleware import TracingMiddleware
from insightai.api.v1.router import api_v1_router
from insightai.domain.exceptions import ConfigurationError
from insightai.infrastructure.ai.factory import build_ai_components
from insightai.infrastructure.chat.bootstrap import build_chat_session_store
from insightai.infrastructure.config.settings import AppEnvironment, get_settings
from insightai.infrastructure.database.bootstrap import (
    build_database_components,
)
from insightai.infrastructure.logging.setup import configure_logging, get_logger
from insightai.infrastructure.observability.bootstrap import build_audit_logger
from insightai.infrastructure.observability.metrics import configure_metrics
from insightai.infrastructure.observability.tracing import configure_tracing, shutdown_tracing
from insightai.infrastructure.ratelimit.bootstrap import build_rate_limiter

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "application_starting",
        version=__version__,
        env=settings.env.value,
        llm_provider=settings.llm_provider.value,
        ai_framework=settings.ai_framework.value,
    )

    app.state.settings = settings

    try:
        app.state.database = build_database_components(settings)
        logger.info("database_configured", kind=app.state.database.config.kind.value)
    except ConfigurationError as exc:
        logger.warning("database_not_configured", error=exc.message)
        app.state.database = None

    shared_validator = app.state.database.validator if app.state.database is not None else None
    app.state.ai = build_ai_components(settings, sql_validator=shared_validator)
    app.state.chat_sessions = build_chat_session_store(settings)
    logger.info(
        "chat_session_store_configured",
        kind=app.state.chat_sessions.kind.value,
    )
    app.state.rate_limit = build_rate_limiter(settings)
    app.state.audit = build_audit_logger(settings)
    logger.info(
        "audit_logger_configured",
        enabled=settings.observability_audit_enabled,
        log_sql=settings.observability_log_sql,
        log_question=settings.observability_log_question,
        llm_usage=settings.observability_llm_usage_enabled,
    )
    tracing_settings = settings.model_copy(
        update={"observability_service_version": __version__},
    )
    app.state.tracing_enabled = configure_tracing(tracing_settings)
    app.state.metrics_enabled = configure_metrics(settings)
    if app.state.metrics_enabled:
        logger.info("prometheus_metrics_enabled", path="/metrics")

    yield

    shutdown_tracing()

    if app.state.database is not None:
        app.state.database.engine.dispose()
        logger.info("database_engine_disposed")

    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Application factory for uvicorn and tests."""
    settings = get_settings()
    app = FastAPI(
        title="InsightAI",
        description="Natural language to SQL agent platform",
        version=__version__,
        lifespan=lifespan,
        debug=settings.debug,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(MetricsMiddleware)
    _configure_development_cors(app, settings)
    register_exception_handlers(app)
    app.include_router(metrics_router)
    app.include_router(api_v1_router)
    return app


def _configure_development_cors(app: FastAPI, settings: object) -> None:
    """Allow the local browser demo UI (``apps/serve_demo.py``) to call the API."""
    from insightai.infrastructure.config.settings import Settings

    assert isinstance(settings, Settings)
    if settings.env != AppEnvironment.DEVELOPMENT:
        return
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def run() -> None:
    """CLI entry: ``python -m insightai.main`` or the ``insightai`` console script."""
    settings = get_settings()
    uvicorn.run(
        "insightai.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )


if __name__ == "__main__":
    run()
