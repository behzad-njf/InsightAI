"""Helpers for optional MSSQL integration tests (Phase 5.5)."""

from __future__ import annotations

import importlib.util
import os

MSSQL_INTEGRATION_URL_ENV = "INSIGHTAI_MSSQL_INTEGRATION_URL"


def mssql_integration_url() -> str | None:
    """Read-only MSSQL URL for integration tests; unset skips the suite."""
    raw = os.environ.get(MSSQL_INTEGRATION_URL_ENV, "").strip()
    return raw or None


def pyodbc_available() -> bool:
    return importlib.util.find_spec("pyodbc") is not None
