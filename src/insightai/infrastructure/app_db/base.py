"""SQLAlchemy declarative base for the InsightAI app database (Phase 16)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class AppBase(DeclarativeBase):
    """Metadata root for platform tables (API keys, feedback, reviews, …)."""

    pass
