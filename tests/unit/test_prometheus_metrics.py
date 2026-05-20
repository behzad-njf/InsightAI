"""Unit tests for Prometheus metrics (Phase 8.4)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from insightai.domain.models.database import DatabaseKind
from insightai.infrastructure.observability import metrics
from insightai.main import create_app
from tests.conftest import make_settings


def _app_settings(*, metrics_enabled: bool):
    return make_settings(
        groq_api_key="gsk-metrics-test",
        openai_api_key="sk-metrics-test",
        database_readonly_url="sqlite:///:memory:",
        database_kind=DatabaseKind.SQLITE,
        observability_metrics_enabled=metrics_enabled,
    )


@contextmanager
def _client_with_settings(settings: object):
    with (
        patch(
            "insightai.infrastructure.config.settings.get_settings",
            return_value=settings,
        ),
        patch("insightai.main.get_settings", return_value=settings),
    ):
        yield


def test_configure_metrics_disabled() -> None:
    settings = _app_settings(metrics_enabled=False)
    assert metrics.configure_metrics(settings) is False
    assert metrics.metrics_active() is False


def test_configure_metrics_warns_without_prometheus_client() -> None:
    settings = _app_settings(metrics_enabled=True)
    with patch.object(metrics, "prometheus_available", return_value=False):
        assert metrics.configure_metrics(settings) is False


def test_record_helpers_noop_when_inactive() -> None:
    metrics.record_http_request(
        method="GET",
        route="/api/v1/chat",
        status_code=200,
        duration_seconds=0.1,
    )
    metrics.record_llm_request(
        provider="groq",
        task="sql_generation",
        duration_seconds=1.0,
        outcome="success",
        prompt_tokens=10,
        completion_tokens=5,
    )
    metrics.record_db_query(db_system="sqlite", duration_seconds=0.05, outcome="success")
    metrics.record_ask_pipeline_stage(stage="sql_generation", duration_seconds=2.0)


def test_render_metrics_after_configure() -> None:
    if not metrics.prometheus_available():
        pytest.skip("prometheus-client not installed")
    settings = _app_settings(metrics_enabled=True)
    try:
        assert metrics.configure_metrics(settings) is True
        payload, content_type = metrics.render_metrics()
        assert b"insightai_http_requests_total" in payload
        assert "text/plain" in content_type
    finally:
        metrics._METRICS_ENABLED = False  # noqa: SLF001
        metrics._registry = None  # noqa: SLF001


def test_metrics_endpoint_404_when_disabled() -> None:
    settings = _app_settings(metrics_enabled=False)
    with _client_with_settings(settings), TestClient(create_app()) as client:
        response = client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.skipif(
    not metrics.prometheus_available(),
    reason="prometheus-client not installed",
)
def test_metrics_endpoint_returns_prometheus_text_when_enabled() -> None:
    settings = _app_settings(metrics_enabled=True)
    with _client_with_settings(settings), TestClient(create_app()) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "insightai_http_requests_total" in response.text
    assert "text/plain" in response.headers["content-type"]
