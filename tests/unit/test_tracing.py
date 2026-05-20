"""Unit tests for OpenTelemetry tracing helpers (Phase 8.3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from insightai.infrastructure.observability import tracing
from tests.conftest import make_settings


def test_configure_tracing_disabled_by_default() -> None:
    settings = make_settings(observability_tracing_enabled=False)
    assert tracing.configure_tracing(settings) is False
    assert tracing.tracing_active() is False


def test_configure_tracing_warns_when_otel_missing() -> None:
    settings = make_settings(observability_tracing_enabled=True)
    with patch.object(tracing, "otel_available", return_value=False):
        assert tracing.configure_tracing(settings) is False
    assert tracing.tracing_active() is False


def test_start_span_noop_when_inactive() -> None:
    with tracing.start_span("test.span", attributes={"foo": "bar"}) as span:
        span.set_attribute("x", 1)
    assert tracing.tracing_active() is False


def test_shutdown_tracing_calls_provider_shutdown() -> None:
    provider = MagicMock()
    tracing._provider = provider  # noqa: SLF001
    tracing._TRACING_ENABLED = True  # noqa: SLF001
    tracing.shutdown_tracing()
    provider.shutdown.assert_called_once()
    assert tracing.tracing_active() is False
