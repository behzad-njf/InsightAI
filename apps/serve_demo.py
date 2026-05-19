#!/usr/bin/env python3
"""
Serve the InsightAI browser demo UI on http://127.0.0.1:8765

Start the API first (development CORS allows this origin):
  uvicorn insightai.main:create_app --factory --reload

Then:
  python apps/serve_demo.py
  # Open http://127.0.0.1:8765
"""

from __future__ import annotations

import http.server
import socketserver
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent / "demo"
PORT = 8765


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(DEMO_DIR), **kwargs)


def main() -> None:
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        url = f"http://127.0.0.1:{PORT}"
        print(f"Serving InsightAI demo UI at {url}")
        print("Ensure the API is running at http://localhost:8000")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
