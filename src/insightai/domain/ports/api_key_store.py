"""Port for platform API key persistence (Phase 16.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from insightai.domain.models.api_key import ApiKey, CreateApiKeyRequest, CreateApiKeyResult


class IApiKeyStore(Protocol):
    """Create, verify, list, and revoke API keys stored in the app database."""

    def create(self, request: CreateApiKeyRequest) -> CreateApiKeyResult:
        """Issue a new key; returns the plaintext secret exactly once."""

    def verify(self, secret: str) -> ApiKey | None:
        """Return key metadata when the secret is valid and active; else ``None``."""

    def revoke(self, *, key_id: str | None = None, key_prefix: str | None = None) -> bool:
        """Revoke by id or prefix. Returns ``False`` if not found."""

    def list_keys(self, *, include_revoked: bool = False) -> list[ApiKey]:
        """List keys (never includes secrets or hashes)."""

    def get_by_id(self, key_id: str) -> ApiKey | None:
        """Fetch metadata by primary key."""
