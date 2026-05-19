"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from insightai.api.auth.dependencies import require_api_auth
from insightai.api.rate_limit import enforce_rate_limit
from insightai.api.v1.routes import ai, ask, chat, health, schema, sql

# Public: probes and LLM smoke test (Phase 1).
public_v1_router = APIRouter(prefix="/api/v1")
public_v1_router.include_router(health.router)
public_v1_router.include_router(ai.router)

# Protected: product + data pipelines (Phase 7.4).
protected_v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[
        Depends(require_api_auth),
        Depends(enforce_rate_limit),
    ],
)
protected_v1_router.include_router(chat.router)
protected_v1_router.include_router(schema.router)
protected_v1_router.include_router(sql.router)
protected_v1_router.include_router(ask.router)

api_v1_router = APIRouter()
api_v1_router.include_router(public_v1_router)
api_v1_router.include_router(protected_v1_router)
