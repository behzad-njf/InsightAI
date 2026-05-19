"""Server-Sent Events (SSE) helpers for streaming API responses."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any


def format_sse(event: str, data: Mapping[str, Any] | None = None) -> str:
    """Format one SSE message (event + JSON data + blank line)."""
    payload = json.dumps(dict(data or {}), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def iter_sse_strings(events: AsyncIterator[str]) -> AsyncIterator[str]:
    """Pass through encoded SSE chunks (extension point for heartbeats)."""
    async for chunk in events:
        yield chunk
