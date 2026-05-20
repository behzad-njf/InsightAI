"""HTTP request tracing middleware (Phase 8.3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.tracing import start_span, tracing_active


class TracingMiddleware(BaseHTTPMiddleware):
    """Create a root ``http.server`` span per request when OpenTelemetry is enabled."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not tracing_active():
            return await call_next(request)

        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        attributes = {
            "http.method": request.method,
            "http.route": route_path,
            "http.target": request.url.path,
            "insightai.request_id": request.headers.get("X-Request-ID"),
        }
        with start_span("http.server", attributes=attributes):
            response = await call_next(request)
            set_attrs = {
                "http.status_code": response.status_code,
                "insightai.request_id": request_id_var.get(),
            }
            from opentelemetry import trace

            span = trace.get_current_span()
            if span.is_recording():
                for key, value in set_attrs.items():
                    if value is not None:
                        span.set_attribute(key, value)
            return response
