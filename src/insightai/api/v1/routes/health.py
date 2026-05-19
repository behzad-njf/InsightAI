"""Health and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from insightai.api.deps import get_health_use_case, get_readiness_use_case
from insightai.api.schemas.common import (
    DatabaseHealthResponse,
    HealthResponse,
    ReadinessResponse,
)
from insightai.application.use_cases.health_check import HealthCheckUseCase
from insightai.application.use_cases.readiness_check import ReadinessCheckUseCase

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def liveness(
    use_case: HealthCheckUseCase = Depends(get_health_use_case),
) -> HealthResponse:
    result = use_case.execute()
    return HealthResponse(status=result.status, version=result.version)


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(
    use_case: ReadinessCheckUseCase = Depends(get_readiness_use_case),
) -> JSONResponse | ReadinessResponse:
    result = use_case.execute()
    db_response = None
    if result.database is not None:
        db_response = DatabaseHealthResponse(
            healthy=result.database.healthy,
            kind=result.database.kind.value,
            latency_ms=result.database.latency_ms,
            message=result.database.message,
        )

    body = ReadinessResponse(
        status=result.status,
        version=result.version,
        database=db_response,
    )
    status_code = (
        status.HTTP_200_OK
        if result.status == "ready"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())
