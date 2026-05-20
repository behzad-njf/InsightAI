"""Schema intelligence routes (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from insightai.api.deps import get_schema_context_use_case
from insightai.api.schemas.schema import SchemaContextResponse
from insightai.application.use_cases.build_schema_context import BuildSchemaContextUseCase
from insightai.domain.models.schema import SchemaContextRequest

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/context", response_model=SchemaContextResponse)
async def get_schema_context(
    question: str = Query(..., min_length=1, description="Natural language question"),
    max_tables: int = Query(12, ge=1, le=50),
    use_case: BuildSchemaContextUseCase = Depends(get_schema_context_use_case),
) -> SchemaContextResponse:
    """
    Return relevant schema context for a question (debug / Phase 3 input).

    Schema markdown is parsed at application startup; context results may be cached (Phase 9.2).
    """
    result = await use_case.execute(
        SchemaContextRequest(question=question, max_tables=max_tables),
    )
    return SchemaContextResponse.from_result(result)
