"""Rate limit bucket key resolution (Phase 16.6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from insightai.domain.models.auth import ApiAuthMode, AuthenticatedPrincipal
from insightai.infrastructure.config.settings import Settings
from insightai.infrastructure.ratelimit.keys import resolve_rate_limit_key
from tests.conftest import make_settings


def test_rate_limit_key_uses_api_key_id() -> None:
    request = MagicMock()
    request.state.principal = AuthenticatedPrincipal(
        subject="Example integration",
        auth_method=ApiAuthMode.API_KEY,
        api_key_id="00000000-0000-0000-0000-000000000099",
    )
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")
    settings = make_settings()
    assert (
        resolve_rate_limit_key(request, settings)
        == "api_key:00000000-0000-0000-0000-000000000099"
    )


def test_rate_limit_key_env_principal_uses_subject() -> None:
    request = MagicMock()
    request.state.principal = AuthenticatedPrincipal(
        subject="api_key_1",
        auth_method=ApiAuthMode.API_KEY,
    )
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")
    settings = Settings(_env_file=None)  # type: ignore[arg-type,call-arg]
    assert resolve_rate_limit_key(request, settings) == "principal:api_key_1"
