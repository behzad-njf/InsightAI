"""API authentication domain models (Phase 7.4, extended Phase 16.4)."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from insightai.domain.models.api_key import ApiKey


class ApiAuthMode(StrEnum):
    """How inbound API requests are authenticated."""

    NONE = "none"
    API_KEY = "api_key"
    JWT = "jwt"


class ApiKeyAuthSource(StrEnum):
    """Where API keys are validated when ``api_auth_mode=api_key``."""

    ENV = "env"
    DATABASE = "database"
    BOTH = "both"


class AuthenticatedPrincipal(BaseModel):
    """Caller identity attached to a request after auth."""

    subject: str = Field(description="API key label, JWT sub, or 'anonymous'.")
    auth_method: ApiAuthMode | str = Field(
        description="none when auth is disabled; otherwise api_key or jwt.",
    )
    api_key_id: str | None = Field(
        default=None,
        description="App DB key UUID when authenticated via stored API key.",
    )
    roles: tuple[str, ...] = ()
    attributes: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    model_config = {"frozen": True}

    @classmethod
    def anonymous(cls) -> Self:
        return cls(subject="anonymous", auth_method=ApiAuthMode.NONE)

    @classmethod
    def from_api_key(cls, key: ApiKey) -> Self:
        """Build principal from a verified app-database API key."""
        return cls(
            subject=key.label,
            auth_method=ApiAuthMode.API_KEY,
            api_key_id=key.id,
            roles=tuple(key.roles),
            attributes={name: tuple(values) for name, values in key.attributes.items()},
        )

    def has_role(self, role: str) -> bool:
        return role.strip().lower() in self.roles

    @classmethod
    def from_jwt_claims(cls, payload: dict[str, object]) -> Self:
        """
        Build principal from JWT claims (Phase 12.5).

        Supported claims:
        - ``sub`` (required by auth layer)
        - ``roles``: string or list of role names
        - ``attributes``: object mapping attribute names to string or list values
        """
        subject = str(payload.get("sub", "")).strip()
        roles = _normalize_claim_roles(payload.get("roles"))
        attributes = _normalize_claim_attributes(payload.get("attributes"))
        return cls(
            subject=subject or "jwt",
            auth_method=ApiAuthMode.JWT,
            roles=roles,
            attributes=attributes,
        )


def _normalize_claim_roles(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    if isinstance(raw, list):
        return tuple(str(item).strip().lower() for item in raw if str(item).strip())
    return ()


def _normalize_claim_attributes(raw: object) -> dict[str, tuple[str, ...]]:
    if raw is None or not isinstance(raw, dict):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            continue
        if isinstance(value, list):
            out[name] = tuple(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str):
            out[name] = tuple(part.strip() for part in value.split(",") if part.strip())
        else:
            text = str(value).strip()
            if text:
                out[name] = (text,)
    return out
