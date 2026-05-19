"""URL helpers for MSSQL credentials."""

from __future__ import annotations

from insightai.infrastructure.config.database_url import (
    mssql_url_with_trust_server_certificate,
    normalize_sqlalchemy_url,
)


def test_normalize_preserves_already_encoded_url() -> None:
    url = "mssql+pyodbc://sa:p%40ss%23word@localhost:1433/campus_analytics?driver=ODBC+Driver+17+for+SQL+Server"
    assert normalize_sqlalchemy_url(url) == url


def test_trust_server_certificate_appended_once() -> None:
    base = "mssql+pyodbc://sa:pass@localhost:1433/campus_analytics?driver=ODBC+Driver+17+for+SQL+Server"
    once = mssql_url_with_trust_server_certificate(base)
    twice = mssql_url_with_trust_server_certificate(once)
    assert once.count("TrustServerCertificate=yes") == 1
    assert twice == once
