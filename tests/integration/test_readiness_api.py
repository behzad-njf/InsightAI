"""Integration tests for readiness edge cases."""

from __future__ import annotations

from insightai.domain.models.database import DatabaseHealthStatus, DatabaseKind


def test_readiness_degraded(api_client) -> None:
    api_client.app.state.database.health_check.check.return_value = (  # type: ignore[attr-defined]
        DatabaseHealthStatus(
            healthy=False,
            kind=DatabaseKind.SQLITE,
            message="db down",
        )
    )
    response = api_client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["healthy"] is False


def test_readiness_without_database(api_client_no_database) -> None:
    response = api_client_no_database.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] is None


def test_request_id_header(api_client) -> None:
    response = api_client.get("/api/v1/health", headers={"X-Request-ID": "test-req-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-req-123"
