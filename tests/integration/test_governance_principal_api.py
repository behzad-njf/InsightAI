"""Integration: API key principal → governance on POST /ask (Phase 12.5)."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from insightai.domain.models.api_key import CreateApiKeyRequest
from insightai.domain.models.auth import ApiAuthMode, ApiKeyAuthSource
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.llm import LLMProviderKind, LLMResponse, TokenUsage
from insightai.infrastructure.app_db.bootstrap import build_app_database_components
from insightai.infrastructure.config.settings import Settings, clear_settings_cache
from insightai.infrastructure.database.bootstrap import build_database_components
from insightai.infrastructure.governance.bootstrap import build_governance_components
from insightai.infrastructure.governance.enforcer import SqlGovernanceEnforcer
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

GOVERNANCE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "governance"
GOVERNED_SQL_JSON = json.dumps(
    {
        "sql": "SELECT id FROM school_school",
        "explanation": "Example scoped query.",
        "confidence": "high",
        "tables_used": ["school_school"],
    },
)


@pytest.fixture
def governance_ask_client(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, str, str], None, None]:
    db_file = tmp_path / "gov_ask.db"
    app_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("INSIGHTAI_APP_DATABASE_URL", app_url)
    clear_settings_cache()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(project_root / "src"))
    command.upgrade(cfg, "head")

    app_db = build_app_database_components(Settings(_env_file=None))  # type: ignore[arg-type,call-arg]
    key_with_scope = app_db.api_key_store.create(
        CreateApiKeyRequest(
            label="Scoped analyst",
            roles=["analyst"],
            attributes={"campus_ids": ["1"]},
        ),
    )
    key_without_scope = app_db.api_key_store.create(
        CreateApiKeyRequest(label="Missing scope", roles=["analyst"], attributes={}),
    )

    settings = Settings(
        _env_file=None,  # type: ignore[arg-type,call-arg]
        groq_api_key="gsk-gov-test",
        api_auth_mode=ApiAuthMode.API_KEY,
        api_key_auth_source=ApiKeyAuthSource.DATABASE,
        database_kind=DatabaseKind.SQLITE,
        database_readonly_url="sqlite:///:memory:",
        governance_enabled=True,
        governance_path=GOVERNANCE_FIXTURE,
    )
    catalog = YamlGovernancePolicyLoader(GOVERNANCE_FIXTURE).load()
    enforcer = SqlGovernanceEnforcer(catalog, database_kind=settings.database_kind)
    db_components = build_database_components(settings)

    mock_framework = MagicMock()
    mock_framework.complete = AsyncMock(
        return_value=LLMResponse(
            content=GOVERNED_SQL_JSON,
            model="test-sql",
            provider=LLMProviderKind.GROQ,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            finish_reason="stop",
        ),
    )

    from insightai.domain.models.answer import AnswerGenerationResult, GenerateAnswerResult
    from insightai.domain.models.database import QueryResult
    from insightai.infrastructure.ai.factory import AIComponents
    from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
    from insightai.infrastructure.prompts.loader import load_sql_generation_prompts

    from insightai.domain.models.answer import AnswerGenerationResult as AnswerPart

    answer_generator = MagicMock()
    answer_generator.generate = AsyncMock(
        return_value=AnswerPart(
            answer="Dry-run ok.",
            row_count=0,
            truncation_noted=False,
        ),
    )

    ai = AIComponents(
        settings=settings,
        llm_provider=MagicMock(),
        framework=mock_framework,
        sql_generator=LLMSQLGenerator(
            mock_framework,
            settings,
            prompt_bundle=load_sql_generation_prompts(settings),
            sql_validator=db_components.validator,
        ),
        answer_generator=answer_generator,
    )

    gov_components = build_governance_components(settings)
    assert isinstance(gov_components.enforcer, SqlGovernanceEnforcer)

    from insightai.main import create_app

    with (
        patch("insightai.main.get_settings", return_value=settings),
        patch("insightai.main.build_ai_components", return_value=ai),
        patch("insightai.main.build_database_components", return_value=db_components),
        patch("insightai.main.build_app_database_components", return_value=app_db),
        patch("insightai.main.build_governance_components", return_value=gov_components),
    ):
        app = create_app()
        with TestClient(app) as client:
            yield (
                client,
                key_with_scope.secret,
                key_without_scope.secret,
            )

    db_components.engine.dispose()


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_ask_dry_run_denies_key_without_scope_attributes(
    governance_ask_client: tuple[TestClient, str, str],
) -> None:
    client, _scoped, unscoped = governance_ask_client
    response = client.post(
        "/api/v1/ask",
        headers={"X-API-Key": unscoped},
        json={"question": "List schools", "mode": "dry_run"},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "GOVERNANCE_DENIED"


def test_ask_dry_run_allows_key_with_scope_attributes(
    governance_ask_client: tuple[TestClient, str, str],
) -> None:
    client, scoped, _unscoped = governance_ask_client
    response = client.post(
        "/api/v1/ask",
        headers={"X-API-Key": scoped},
        json={"question": "List schools", "mode": "dry_run"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert "school_school" in data["sql"].lower()
