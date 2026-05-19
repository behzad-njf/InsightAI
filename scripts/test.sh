#!/usr/bin/env bash
# Run the full local quality gate (same as CI).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "==> ruff"
ruff check src tests

echo "==> mypy"
mypy src

echo "==> pytest"
pytest tests \
  --cov=insightai \
  --cov-report=term-missing \
  -q "$@"

echo "==> done"
