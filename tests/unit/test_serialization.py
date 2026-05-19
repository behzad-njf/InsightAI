"""Unit tests for query result serialization."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from insightai.infrastructure.database.serialization import serialize_value


def test_serialize_primitives() -> None:
    assert serialize_value(None) is None
    assert serialize_value("text") == "text"
    assert serialize_value(42) == 42


def test_serialize_decimal_and_datetime() -> None:
    assert serialize_value(Decimal("19.99")) == "19.99"
    dt = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert serialize_value(dt) == dt.isoformat()


def test_serialize_uuid_and_bytes() -> None:
    value = UUID("12345678-1234-5678-1234-567812345678")
    assert serialize_value(value) == str(value)
    assert isinstance(serialize_value(b"abc"), str)
