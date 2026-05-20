"""Prometheus metrics scrape endpoint (Phase 8.4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from insightai.infrastructure.observability.metrics import metrics_active, render_metrics

router = APIRouter(tags=["observability"], include_in_schema=False)


@router.get("/metrics")
def prometheus_metrics() -> Response:
    """
    Prometheus exposition format (``text/plain``).

    Public, unauthenticated — intended for in-cluster scrapers only.
    Enable with ``INSIGHTAI_OBSERVABILITY_METRICS_ENABLED=true`` and
    ``pip install insightai[prometheus]``.
    """
    if not metrics_active():
        raise HTTPException(status_code=404, detail="Metrics are not enabled.")
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
