"""Platform API key domain models (Phase 16.2)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from insightai.domain.models.governance import Principal

__all__ = [
    "ApiKey",
    "CreateApiKeyRequest",
    "CreateApiKeyResult",
    "PlatformRole",
    "Principal",
    "parse_attributes_json",
    "parse_roles_arg",
]


class PlatformRole(StrEnum):
    """Common platform roles; additional string roles are allowed in YAML/CLI."""

    ANALYST = "analyst"
    ADMIN = "admin"


class ApiKey(BaseModel):
    """Stored API key metadata (never includes the secret or hash)."""

    id: str = Field(description="Stable UUID for this key.")
    key_prefix: str = Field(
        min_length=8,
        max_length=32,
        description="Public prefix embedded in the key token (lookup id).",
    )
    label: str = Field(min_length=1, max_length=255, description="Human label for operators.")
    roles: list[str] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Scope dimensions for governance, e.g. campus_ids: ['1','2'].",
    )
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"frozen": True}

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("roles", mode="before")
    @classmethod
    def normalize_roles(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip().lower() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        msg = f"roles must be a list or comma-separated string, got {type(value)!r}"
        raise TypeError(msg)

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            msg = f"attributes must be a dict, got {type(value)!r}"
            raise TypeError(msg)
        out: dict[str, list[str]] = {}
        for key, raw in value.items():
            name = str(key).strip()
            if not name:
                continue
            if isinstance(raw, list):
                out[name] = [str(item).strip() for item in raw if str(item).strip()]
            elif isinstance(raw, str):
                out[name] = [part.strip() for part in raw.split(",") if part.strip()]
            else:
                out[name] = [str(raw).strip()] if str(raw).strip() else []
        return out

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import UTC

        return datetime.now(UTC) >= self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired


class CreateApiKeyRequest(BaseModel):
    """Input for issuing a new API key."""

    label: str = Field(min_length=1, max_length=255)
    roles: list[str] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    expires_at: datetime | None = None

    model_config = {"frozen": True}

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "label must not be empty"
            raise ValueError(msg)
        return stripped


class CreateApiKeyResult(BaseModel):
    """Result of key creation — ``secret`` is shown only once."""

    api_key: ApiKey
    secret: str = Field(description="Full API key token; store nowhere after display.")

    model_config = {"frozen": True}


def parse_roles_arg(value: str | None) -> list[str]:
    """Parse ``--roles analyst,admin`` for CLI."""
    if not value or not value.strip():
        return [PlatformRole.ANALYST.value]
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def parse_attributes_json(value: str | None) -> dict[str, list[str]]:
    """Parse ``--attributes '{"campus_ids":["1"]}'`` for CLI."""
    if not value or not value.strip():
        return {}
    import json

    parsed: Any = json.loads(value)
    if not isinstance(parsed, dict):
        msg = "attributes JSON must be an object"
        raise ValueError(msg)
    return CreateApiKeyRequest(
        label="validate",
        roles=[],
        attributes=parsed,  # type: ignore[arg-type]
    ).attributes


def parse_attributes_arg(value: str | None) -> dict[str, list[str]]:
    """
    Parse CLI ``--attributes`` (Phase 12.5).

    Accepts JSON object or comma-separated ``key=value`` pairs::

        campus_ids=1,2
        campus_ids=1,2,region_ids=west
    """
    if not value or not value.strip():
        return {}
    text = value.strip()
    if text.startswith("{"):
        return parse_attributes_json(text)
    parsed: dict[str, list[str]] = {}
    segments: list[str] = []
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "=" in piece or not segments:
            segments.append(piece)
        else:
            segments[-1] = f"{segments[-1]},{piece}"
    for piece in segments:
        if "=" not in piece:
            msg = (
                f"Invalid attributes segment {piece!r}; "
                "use key=value or JSON object"
            )
            raise ValueError(msg)
        key, raw_values = piece.split("=", 1)
        name = key.strip()
        if not name:
            msg = "Attribute name must not be empty"
            raise ValueError(msg)
        if "|" in raw_values:
            values = [v.strip() for v in raw_values.split("|") if v.strip()]
        else:
            values = [v.strip() for v in raw_values.split(",") if v.strip()]
        parsed[name] = values if values else [raw_values.strip()]
    return CreateApiKeyRequest(
        label="validate",
        roles=[],
        attributes=parsed,
    ).attributes
