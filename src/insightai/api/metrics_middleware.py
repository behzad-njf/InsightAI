"""HTTP Prometheus metrics middleware (Phase 8.4)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from insightai.infrastructure.observability.metrics import (
    _normalize_route,
    metrics_active,
    record_http_request,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and latency histograms for product API routes."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not metrics_active():
            return await call_next(request)

        route = request.scope.get("route")
        route_path = _normalize_route(request.url.path, getattr(route, "path", None))
        started = time.perf_counter()
        response = await call_next(request)
        duration_seconds = time.perf_counter() - started
        record_http_request(
            method=request.method,
            route=route_path,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        return response
