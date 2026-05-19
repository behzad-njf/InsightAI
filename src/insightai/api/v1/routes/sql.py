"""SQL generation routes (Phase 3 debug API)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from insightai.api.deps import get_generate_sql_use_case
from insightai.api.schemas.sql_generation import SQLGenerateRequest, SQLGenerateResponse
from insightai.application.use_cases.generate_sql import GenerateSQLUseCase

router = APIRouter(prefix="/sql", tags=["sql"])


@router.post("/generate", response_model=SQLGenerateResponse)
async def generate_sql(
    body: SQLGenerateRequest,
    use_case: GenerateSQLUseCase = Depends(get_generate_sql_use_case),
) -> SQLGenerateResponse:
    """
    Generate a read-only SQL query from a natural language question.

    Orchestrates Phase 2 schema context retrieval and Phase 3 LLM SQL generation.
    Does **not** execute SQL against the database (Phase 5).
    """
    result = await use_case.execute(body.to_domain())
    return SQLGenerateResponse.from_domain(result)
