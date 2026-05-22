"""ORM model for platform API keys (Phase 16.2)."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from insightai.infrastructure.app_db.base import AppBase


class ApiKeyRecord(AppBase):
    """Persisted API key — secret stored as bcrypt hash only."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key_prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @staticmethod
    def dump_roles(roles: list[str]) -> str:
        return json.dumps(roles)

    @staticmethod
    def dump_attributes(attributes: dict[str, list[str]]) -> str:
        return json.dumps(attributes)

    @staticmethod
    def load_roles(raw: str) -> list[str]:
        data = json.loads(raw or "[]")
        if not isinstance(data, list):
            return []
        return [str(item) for item in data]

    @staticmethod
    def load_attributes(raw: str) -> dict[str, list[str]]:
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            return {}
        out: dict[str, list[str]] = {}
        for key, value in data.items():
            name = str(key)
            if isinstance(value, list):
                out[name] = [str(item) for item in value]
            elif isinstance(value, str):
                out[name] = [value]
            else:
                out[name] = [str(value)]
        return out
