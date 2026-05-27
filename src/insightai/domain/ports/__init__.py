"""Domain ports (interfaces) for infrastructure adapters."""

from insightai.domain.ports.ai_framework import IAIFramework
from insightai.domain.ports.ask_pipeline import IAskPipeline
from insightai.domain.ports.database import (
    IDatabaseConnectionFactory,
    IDatabaseHealthCheck,
    IReadOnlyQueryExecutor,
)
from insightai.domain.ports.explainability_builder import IExplainabilityBuilder
from insightai.domain.ports.llm_provider import ILLMProvider
from insightai.domain.ports.schema_repository import ISchemaRepository
from insightai.domain.ports.sql_generator import ISQLGenerator
from insightai.domain.ports.sql_safety import ISQLSafetyValidator

__all__ = [
    "IExplainabilityBuilder",
    "IAskPipeline",
    "IAIFramework",
    "IDatabaseConnectionFactory",
    "IDatabaseHealthCheck",
    "ILLMProvider",
    "IReadOnlyQueryExecutor",
    "ISchemaRepository",
    "ISQLGenerator",
    "ISQLSafetyValidator",
]
