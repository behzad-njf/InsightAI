"""Build rate-limit bucket keys from requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from insightai.domain.models.auth import ApiAuthMode, AuthenticatedPrincipal

if TYPE_CHECKING:
    from starlette.requests import Request

    from insightai.infrastructure.config.settings import Settings


def resolve_rate_limit_key(request: Request, settings: Settings) -> str:
    """
    Bucket key: authenticated ``principal:{subject}`` else ``ip:{address}``.

    Uses the first ``X-Forwarded-For`` hop when ``rate_limit_trust_forwarded_for`` is set.
    """
    principal: AuthenticatedPrincipal | None = getattr(request.state, "principal", None)
    if principal is not None and principal.auth_method != ApiAuthMode.NONE:
        return f"principal:{principal.subject}"

    return f"ip:{_client_ip(request, settings)}"


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"
