"""Integration tests for schema context API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_schema_context_endpoint(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/schema/context",
        params={"question": "children in a classroom", "max_tables": 12},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "children in a classroom"
    assert "accounts_user" in data["table_names"]
    assert any(name.startswith("school_") for name in data["table_names"])
    assert "accounts_user" in data["context_markdown"]
    assert isinstance(data["join_pattern_titles"], list)
