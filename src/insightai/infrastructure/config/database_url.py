"""SQLAlchemy URL normalization for ODBC/MSSQL credentials."""

from __future__ import annotations

from sqlalchemy.engine import make_url


def normalize_sqlalchemy_url(url: str) -> str:
    """
    Re-render a SQLAlchemy URL with properly encoded username/password.

    Use when ``INSIGHTAI_DATABASE_READONLY_URL`` contains special characters
    (``@``, ``#``, ``&``, etc.) that break manual URL strings.
    """
    stripped = url.strip()
    parsed = make_url(stripped)
    return parsed.render_as_string(hide_password=False)


def mssql_url_with_trust_server_certificate(url: str) -> str:
    """Append ``TrustServerCertificate=yes`` for local/Docker SQL Server if missing."""
    if "trustservercertificate" in url.lower():
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}TrustServerCertificate=yes"
