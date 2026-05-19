"""Integration tests for health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_readiness_ready(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"]["healthy"] is True
