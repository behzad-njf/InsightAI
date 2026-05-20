"""HTTP middleware."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from insightai.infrastructure.logging.setup import request_id_var
from insightai.infrastructure.observability.context import audit_context_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID and reset audit context for each request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_token = request_id_var.set(request_id)
        audit_token = audit_context_var.set(None)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(request_token)
            audit_context_var.reset(audit_token)
        response.headers["X-Request-ID"] = request_id
        return response
