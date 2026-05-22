"""Wire platform app database components (Phase 16.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightai.infrastructure.app_db.api_key_store import SqlApiKeyStore
from insightai.infrastructure.app_db.engine import create_app_database_engine
from insightai.infrastructure.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from insightai.domain.ports.api_key_store import IApiKeyStore


@dataclass(frozen=True)
class AppDatabaseComponents:
    """Bundled app DB engine and stores for DI / FastAPI lifespan."""

    url: str
    engine: Engine
    api_key_store: IApiKeyStore


def build_app_database_components(
    settings: Settings | None = None,
) -> AppDatabaseComponents:
    """Create the platform database engine and API key store from settings."""
    settings = settings or get_settings()
    url = settings.resolved_app_database_url()
    engine = create_app_database_engine(settings)
    return AppDatabaseComponents(
        url=url,
        engine=engine,
        api_key_store=SqlApiKeyStore(engine),
    )
