"""Integration tests for schema context API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_schema_context_endpoint(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/schema/context",
        params={"question": "orders per customer", "max_tables": 12},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "orders per customer"
    assert "demo_customers" in data["table_names"]
    assert "demo_orders" in data["table_names"]
    assert "demo_customers" in data["context_markdown"]
    assert isinstance(data["join_pattern_titles"], list)
