"""OpenTelemetry tracing (Phase 8.3) — optional ``insightai[otel]`` extra."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from insightai.infrastructure.logging.setup import get_logger

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from insightai.infrastructure.config.settings import Settings

logger = get_logger(__name__)

_TRACING_ENABLED = False
_OTEL_AVAILABLE: bool | None = None
_provider: object | None = None


class _NoOpSpan:
    """Stand-in when tracing is disabled or OpenTelemetry is not installed."""

    def set_attribute(self, key: str, value: object) -> None:
        return

    def set_status(self, *_args: object, **_kwargs: object) -> None:
        return

    def record_exception(self, *_args: object, **_kwargs: object) -> None:
        return


def otel_available() -> bool:
    """Return True when OpenTelemetry SDK packages are importable."""
    global _OTEL_AVAILABLE
    if _OTEL_AVAILABLE is None:
        try:
            import opentelemetry.sdk.trace  # noqa: F401
        except ImportError:
            _OTEL_AVAILABLE = False
        else:
            _OTEL_AVAILABLE = True
    return _OTEL_AVAILABLE


def tracing_active() -> bool:
    return _TRACING_ENABLED


def configure_tracing(settings: Settings) -> bool:
    """
    Configure the global tracer provider when tracing is enabled.

    Returns True when tracing is active. Requires ``pip install insightai[otel]``.
    """
    global _TRACING_ENABLED, _provider

    if not settings.observability_tracing_enabled:
        return False

    if not otel_available():
        logger.warning(
            "opentelemetry_not_installed",
            hint="pip install 'insightai[otel]' to export traces",
        )
        return False

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create(
        {
            "service.name": settings.observability_service_name,
            "service.version": settings.observability_service_version,
        },
    )
    provider = TracerProvider(resource=resource)

    if settings.observability_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=settings.observability_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        export_target = settings.observability_otlp_endpoint
    elif settings.env.value == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        export_target = "console"
    else:
        logger.warning(
            "tracing_no_exporter",
            message=(
                "INSIGHTAI_OBSERVABILITY_TRACING_ENABLED=true but no OTLP endpoint; "
                "set INSIGHTAI_OBSERVABILITY_OTLP_ENDPOINT or use development env."
            ),
        )
        return False

    trace.set_tracer_provider(provider)
    _provider = provider
    _TRACING_ENABLED = True
    logger.info(
        "tracing_configured",
        service=settings.observability_service_name,
        export=export_target,
    )
    return True


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider (application shutdown)."""
    global _TRACING_ENABLED, _provider
    if _provider is not None and hasattr(_provider, "shutdown"):
        _provider.shutdown()
    _provider = None
    _TRACING_ENABLED = False


def _normalize_attributes(
    attributes: Mapping[str, object] | None,
) -> dict[str, str | int | float | bool]:
    if not attributes:
        return {}
    normalized: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


@contextmanager
def start_span(
    name: str,
    *,
    attributes: Mapping[str, object] | None = None,
) -> Generator[Any, None, None]:
    """
    Start a child span when tracing is active; otherwise yield a no-op span.

    Exceptions are recorded on the span before re-raising.
    """
    if not _TRACING_ENABLED:
        yield _NoOpSpan()
        return

    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    tracer = trace.get_tracer("insightai")
    with tracer.start_as_current_span(name) as span:
        for key, value in _normalize_attributes(attributes).items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            if span.is_recording():
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def set_span_attributes(attributes: Mapping[str, object]) -> None:
    """Set attributes on the current span when tracing is active."""
    if not _TRACING_ENABLED:
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    if not span.is_recording():
        return
    for key, value in _normalize_attributes(attributes).items():
        span.set_attribute(key, value)
