"""Helpers for parsing Server-Sent Events in integration tests."""

from __future__ import annotations

import json


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse raw SSE text into ``(event_name, data_dict)`` pairs."""
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and current_event:
            events.append((current_event, json.loads(line.removeprefix("data: "))))
            current_event = None
    return events
