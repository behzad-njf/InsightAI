"""Factory for LLM providers and AI framework adapters."""

from __future__ import annotations

from dataclasses import dataclass

from insightai.domain.exceptions import LLMConfigurationError
from insightai.domain.models.llm import AIFrameworkKind, LLMProviderKind
from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.answer_generator import IAnswerGenerator
from insightai.domain.ports.llm_provider import ILLMProvider
from insightai.domain.ports.sql_generator import ISQLGenerator
from insightai.domain.ports.sql_safety import ISQLSafetyValidator
from insightai.infrastructure.ai.answer_generator import LLMAnswerGenerator
from insightai.infrastructure.ai.frameworks.langchain_adapter import LangChainFrameworkAdapter
from insightai.infrastructure.ai.frameworks.llamaindex_adapter import (
    LlamaIndexFrameworkAdapter,
)
from insightai.infrastructure.ai.langchain.availability import langchain_available
from insightai.infrastructure.ai.providers.groq_provider import GroqLLMProvider
from insightai.infrastructure.ai.providers.observing_provider import ObservingLLMProvider
from insightai.infrastructure.ai.providers.openai_provider import OpenAILLMProvider
from insightai.infrastructure.ai.providers.openrouter_provider import OpenRouterLLMProvider
from insightai.infrastructure.ai.sql_generator import LLMSQLGenerator
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.observability.bootstrap import build_audit_logger
from insightai.infrastructure.security.composite_sql_validator import create_sql_safety_validator


@dataclass(frozen=True)
class AIComponents:
    """Bundled AI infrastructure for DI / FastAPI deps (Step 7)."""

    settings: Settings
    llm_provider: ILLMProvider
    framework: IAIFramework
    sql_generator: ISQLGenerator
    answer_generator: IAnswerGenerator


def create_raw_llm_provider(settings: Settings | None = None) -> ILLMProvider:
    """Instantiate the configured SDK provider without observability wrapping."""
    settings = settings or get_settings()
    if settings.llm_provider == LLMProviderKind.GROQ:
        return GroqLLMProvider(settings)
    if settings.llm_provider == LLMProviderKind.OPENAI:
        return OpenAILLMProvider(settings)
    if settings.llm_provider == LLMProviderKind.OPENROUTER:
        return OpenRouterLLMProvider(settings)
    msg = f"Unsupported LLM provider: {settings.llm_provider}"
    raise LLMConfigurationError(msg)


def create_llm_provider(settings: Settings | None = None) -> ILLMProvider:
    """Instantiate the configured LLM provider (``INSIGHTAI_LLM_PROVIDER``)."""
    settings = settings or get_settings()
    raw = create_raw_llm_provider(settings)
    if settings.observability_audit_enabled and settings.observability_llm_usage_enabled:
        return ObservingLLMProvider(raw, settings, build_audit_logger(settings))
    return raw


def create_ai_framework(
    provider: ILLMProvider | None = None,
    settings: Settings | None = None,
) -> IAIFramework:
    """Instantiate the configured AI framework (``INSIGHTAI_AI_FRAMEWORK``)."""
    settings = settings or get_settings()
    provider = provider or create_llm_provider(settings)

    if settings.ai_framework == AIFrameworkKind.LLAMAINDEX:
        return LlamaIndexFrameworkAdapter(provider, settings)
    if settings.ai_framework == AIFrameworkKind.LANGCHAIN:
        if not langchain_available():
            msg = (
                "INSIGHTAI_AI_FRAMEWORK=langchain requires LangChain packages. "
                "Install with: pip install 'insightai[langchain]'"
            )
            raise LLMConfigurationError(msg)
        return LangChainFrameworkAdapter(provider, settings)
    msg = f"Unsupported AI framework: {settings.ai_framework}"
    raise LLMConfigurationError(msg)


def create_sql_generator(
    framework: IAIFramework | None = None,
    settings: Settings | None = None,
    *,
    sql_validator: ISQLSafetyValidator | None = None,
) -> ISQLGenerator:
    """Instantiate the LLM SQL generator (Phase 3.3)."""
    settings = settings or get_settings()
    framework = framework or create_ai_framework(settings=settings)
    validator = sql_validator or create_sql_safety_validator(settings=settings)
    return LLMSQLGenerator(framework, settings, sql_validator=validator)


def create_answer_generator(
    framework: IAIFramework | None = None,
    settings: Settings | None = None,
) -> IAnswerGenerator:
    """Instantiate the LLM answer generator (Phase 6.2)."""
    settings = settings or get_settings()
    framework = framework or create_ai_framework(settings=settings)
    return LLMAnswerGenerator(framework, settings)


def build_ai_components(
    settings: Settings | None = None,
    *,
    sql_validator: ISQLSafetyValidator | None = None,
) -> AIComponents:
    """Create provider + framework from settings."""
    settings = settings or get_settings()
    provider = create_llm_provider(settings)
    framework = create_ai_framework(provider, settings)
    sql_generator = create_sql_generator(
        framework,
        settings,
        sql_validator=sql_validator,
    )
    answer_generator = create_answer_generator(framework, settings)
    return AIComponents(
        settings=settings,
        llm_provider=provider,
        framework=framework,
        sql_generator=sql_generator,
        answer_generator=answer_generator,
    )
