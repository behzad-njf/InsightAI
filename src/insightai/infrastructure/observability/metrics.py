"""Prometheus metrics (Phase 8.4) — optional ``insightai[prometheus]`` extra."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

logger = get_logger(__name__)

_METRICS_ENABLED = False
_PROMETHEUS_AVAILABLE: bool | None = None
_registry: CollectorRegistry | None = None

# Metric handles (populated when enabled; typed as Any for optional prometheus_client).
_http_requests_total: Any = None
_http_request_duration_seconds: Any = None
_llm_requests_total: Any = None
_llm_request_duration_seconds: Any = None
_llm_tokens_total: Any = None
_db_queries_total: Any = None
_db_query_duration_seconds: Any = None
_ask_pipeline_duration_seconds: Any = None


def prometheus_available() -> bool:
    global _PROMETHEUS_AVAILABLE
    if _PROMETHEUS_AVAILABLE is None:
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            _PROMETHEUS_AVAILABLE = False
        else:
            _PROMETHEUS_AVAILABLE = True
    return _PROMETHEUS_AVAILABLE


def metrics_active() -> bool:
    return _METRICS_ENABLED


def configure_metrics(settings: object) -> bool:
    """Register Prometheus collectors when metrics are enabled."""
    global _METRICS_ENABLED, _registry  # noqa: PLW0603
    global _http_requests_total, _http_request_duration_seconds  # noqa: PLW0603
    global _llm_requests_total, _llm_request_duration_seconds, _llm_tokens_total  # noqa: PLW0603
    global _db_queries_total, _db_query_duration_seconds  # noqa: PLW0603
    global _ask_pipeline_duration_seconds  # noqa: PLW0603

    from insightai.infrastructure.config.settings import Settings

    assert isinstance(settings, Settings)

    if not settings.observability_metrics_enabled:
        return False

    if not prometheus_available():
        logger.warning(
            "prometheus_client_not_installed",
            hint="pip install 'insightai[prometheus]' to expose /metrics",
        )
        return False

    from prometheus_client import CollectorRegistry, Counter, Histogram

    registry = CollectorRegistry()

    _http_requests_total = Counter(
        "insightai_http_requests_total",
        "Total HTTP requests handled by the API.",
        labelnames=("method", "route", "status"),
        registry=registry,
    )
    _http_request_duration_seconds = Histogram(
        "insightai_http_request_duration_seconds",
        "HTTP request latency in seconds.",
        labelnames=("method", "route"),
        registry=registry,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 120.0),
    )
    _llm_requests_total = Counter(
        "insightai_llm_requests_total",
        "Total LLM provider calls.",
        labelnames=("provider", "task", "outcome"),
        registry=registry,
    )
    _llm_request_duration_seconds = Histogram(
        "insightai_llm_request_duration_seconds",
        "LLM call latency in seconds.",
        labelnames=("provider", "task"),
        registry=registry,
        buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    )
    _llm_tokens_total = Counter(
        "insightai_llm_tokens_total",
        "LLM token usage by kind.",
        labelnames=("provider", "task", "kind"),
        registry=registry,
    )
    _db_queries_total = Counter(
        "insightai_db_queries_total",
        "Read-only database queries executed.",
        labelnames=("db_system", "outcome"),
        registry=registry,
    )
    _db_query_duration_seconds = Histogram(
        "insightai_db_query_duration_seconds",
        "Database query latency in seconds.",
        labelnames=("db_system",),
        registry=registry,
        buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 30.0, 120.0),
    )
    _ask_pipeline_duration_seconds = Histogram(
        "insightai_ask_pipeline_duration_seconds",
        "Ask pipeline stage latency in seconds.",
        labelnames=("stage",),
        registry=registry,
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    )

    _registry = registry
    _METRICS_ENABLED = True
    logger.info("prometheus_metrics_configured")
    return True


def render_metrics() -> tuple[bytes, str]:
    """Return Prometheus exposition payload and content type."""
    if _registry is None:
        return b"", "text/plain; version=0.0.4; charset=utf-8"
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return generate_latest(_registry), CONTENT_TYPE_LATEST


def _normalize_route(request_path: str, route_path: str | None) -> str:
    if route_path:
        return route_path
    if request_path == "/metrics":
        return "/metrics"
    return "unmatched"


def should_record_http_metric(path: str) -> bool:
    """Skip noise from docs, probes, and the metrics scrape itself."""
    if path in {"/metrics", "/openapi.json", "/docs", "/redoc"}:
        return False
    return not path.startswith("/health")


def record_http_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    if not _METRICS_ENABLED or not should_record_http_metric(route):
        return
    assert _http_requests_total is not None
    assert _http_request_duration_seconds is not None
    status = str(status_code)
    _http_requests_total.labels(method=method, route=route, status=status).inc()
    _http_request_duration_seconds.labels(method=method, route=route).observe(duration_seconds)


def record_llm_request(
    *,
    provider: str,
    task: str | None,
    duration_seconds: float,
    outcome: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    if not _METRICS_ENABLED:
        return
    assert _llm_requests_total is not None
    assert _llm_request_duration_seconds is not None
    assert _llm_tokens_total is not None
    task_label = task or "unknown"
    _llm_requests_total.labels(provider=provider, task=task_label, outcome=outcome).inc()
    _llm_request_duration_seconds.labels(provider=provider, task=task_label).observe(
        duration_seconds,
    )
    if prompt_tokens is not None:
        _llm_tokens_total.labels(provider=provider, task=task_label, kind="prompt").inc(
            prompt_tokens,
        )
    if completion_tokens is not None:
        _llm_tokens_total.labels(provider=provider, task=task_label, kind="completion").inc(
            completion_tokens,
        )


def record_db_query(
    *,
    db_system: str,
    duration_seconds: float,
    outcome: str,
) -> None:
    if not _METRICS_ENABLED:
        return
    assert _db_queries_total is not None
    assert _db_query_duration_seconds is not None
    _db_queries_total.labels(db_system=db_system, outcome=outcome).inc()
    _db_query_duration_seconds.labels(db_system=db_system).observe(duration_seconds)


def record_ask_pipeline_stage(*, stage: str, duration_seconds: float) -> None:
    if not _METRICS_ENABLED:
        return
    assert _ask_pipeline_duration_seconds is not None
    _ask_pipeline_duration_seconds.labels(stage=stage).observe(duration_seconds)
