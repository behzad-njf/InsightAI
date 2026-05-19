#!/usr/bin/env python3
"""
Ask InsightAI a question via the running API.

Usage:
  # API must be running first:
  #   uvicorn insightai.main:create_app --factory --reload

  python scripts/ask.py "How many active classrooms are there?"
  python scripts/ask.py --stream "How many students per classroom?"
  python scripts/ask.py                    # interactive mode
  python scripts/ask.py --include-sql "…"

Environment:
  INSIGHTAI_API_URL   default http://localhost:8000
  INSIGHTAI_API_KEY   sent as X-API-Key when API auth is enabled
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8000"


def _api_url() -> str:
    return os.environ.get("INSIGHTAI_API_URL", DEFAULT_API_URL).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("INSIGHTAI_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _check_health(client: httpx.Client, base: str) -> None:
    try:
        response = client.get(f"{base}/api/v1/health", timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(
            f"Cannot reach API at {base} ({exc}).\n"
            "Start the server first, for example:\n"
            "  uvicorn insightai.main:create_app --factory --reload",
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    current: str | None = None
    for line in body.split("\n"):
        if line.startswith("event: "):
            current = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and current:
            events.append((current, json.loads(line.removeprefix("data: "))))
            current = None
    return events


def _print_answer(data: dict[str, Any], *, include_sql: bool) -> None:
    print()
    print(data.get("answer", "").strip())
    print()
    print(
        f"Rows: {data.get('row_count', '?')}"
        + (" (truncated)" if data.get("truncation_noted") else "")
    )
    timings = data.get("timings") or {}
    if timings:
        print(
            f"Time: {timings.get('total_ms', '?')} ms "
            f"(sql {timings.get('sql_generation_ms', '?')} | "
            f"db {timings.get('query_execution_ms', '?')} | "
            f"answer {timings.get('answer_generation_ms', '?')})"
        )
    if include_sql and data.get("sql"):
        print()
        print("SQL:")
        print(data["sql"])
    if data.get("request_id"):
        print(f"Request ID: {data['request_id']}")


def ask_sync(
    client: httpx.Client,
    base: str,
    question: str,
    *,
    include_sql: bool,
    timeout: float,
) -> None:
    payload: dict[str, Any] = {"question": question}
    if include_sql:
        payload["include_sql"] = True

    print("Thinking…", flush=True)
    response = client.post(
        f"{base}/api/v1/chat",
        headers=_headers(),
        json=payload,
        timeout=timeout,
    )
    if response.status_code == 401:
        print(
            "Unauthorized. Set INSIGHTAI_API_KEY or disable auth (INSIGHTAI_API_AUTH_MODE=none).",
            file=sys.stderr,
        )
        sys.exit(1)
    if response.status_code >= 400:
        print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)

    _print_answer(response.json(), include_sql=include_sql)


def ask_stream(
    client: httpx.Client,
    base: str,
    question: str,
    *,
    include_sql: bool,
    timeout: float,
) -> None:
    payload: dict[str, Any] = {"question": question}
    if include_sql:
        payload["include_sql"] = True

    phases = {
        "generating_sql": "Generating SQL…",
        "executing_query": "Running query…",
        "generating_answer": "Writing answer…",
    }
    answer_parts: list[str] = []

    with client.stream(
        "POST",
        f"{base}/api/v1/chat/stream",
        headers=_headers(),
        json=payload,
        timeout=timeout,
    ) as response:
        if response.status_code == 401:
            print(
                "Unauthorized. Set INSIGHTAI_API_KEY or disable auth.",
                file=sys.stderr,
            )
            sys.exit(1)
        if response.status_code == 404:
            print(
                "Streaming disabled. Set INSIGHTAI_CHAT_STREAMING_ENABLED=true in .env",
                file=sys.stderr,
            )
            sys.exit(1)
        if response.status_code >= 400:
            print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
            sys.exit(1)

        current_event: str | None = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
            elif line.startswith("data: ") and current_event:
                data = json.loads(line.removeprefix("data: "))
                if current_event == "status":
                    phase = data.get("phase", "")
                    print(phases.get(phase, phase), flush=True)
                elif current_event == "token":
                    text = data.get("text", "")
                    answer_parts.append(text)
                    print(text, end="", flush=True)
                elif current_event == "error":
                    print(
                        f"\nError: {data.get('error_message')} ({data.get('error_code')})",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                elif current_event == "done":
                    if not answer_parts:
                        print(data.get("answer", ""), end="", flush=True)
                    print()
                    _print_answer(data, include_sql=include_sql)
                current_event = None


def _interactive(args: argparse.Namespace) -> None:
    base = _api_url()
    print(f"InsightAI — interactive mode ({base})")
    print("Enter a question (empty line or Ctrl+C to quit).\n")

    timeout = httpx.Timeout(args.timeout)
    with httpx.Client(timeout=timeout) as client:
        _check_health(client, base)
        while True:
            try:
                question = input("Question> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not question:
                break
            if args.stream:
                ask_stream(
                    client,
                    base,
                    question,
                    include_sql=args.include_sql,
                    timeout=args.timeout,
                )
            else:
                ask_sync(
                    client,
                    base,
                    question,
                    include_sql=args.include_sql,
                    timeout=args.timeout,
                )
            print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask InsightAI a natural language question (requires running API).",
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Question text. Omit for interactive mode.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use POST /api/v1/chat/stream (live tokens + status).",
    )
    parser.add_argument(
        "--include-sql",
        action="store_true",
        help="Include generated SQL in the response.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"API base URL (default: {DEFAULT_API_URL} or INSIGHTAI_API_URL).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP timeout in seconds (default 300).",
    )
    args = parser.parse_args()

    if args.api_url:
        os.environ["INSIGHTAI_API_URL"] = args.api_url.rstrip("/")

    if not args.question:
        _interactive(args)
        return

    base = _api_url()
    timeout = httpx.Timeout(args.timeout)
    with httpx.Client(timeout=timeout) as client:
        _check_health(client, base)
        if args.stream:
            ask_stream(
                client,
                base,
                args.question,
                include_sql=args.include_sql,
                timeout=args.timeout,
            )
        else:
            ask_sync(
                client,
                base,
                args.question,
                include_sql=args.include_sql,
                timeout=args.timeout,
            )


if __name__ == "__main__":
    main()
