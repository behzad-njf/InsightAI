#!/usr/bin/env bash
# Build and smoke-test the Docker Compose stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and set GROQ_API_KEY" >&2
  exit 1
fi

echo "==> docker compose build"
docker compose build

echo "==> docker compose up -d"
docker compose up -d

cleanup() {
  docker compose down
}
trap cleanup EXIT

echo "==> waiting for API health"
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

export INSIGHTAI_SMOKE_URL=http://localhost:8000
export INSIGHTAI_SMOKE_REQUIRE_LLM="${INSIGHTAI_SMOKE_REQUIRE_LLM:-false}"
bash scripts/smoke_api.sh

echo "==> optional SQL check against compose postgres"
docker compose exec -T postgres \
  psql -U insightai -d insightai -c "SELECT id, email FROM accounts_user LIMIT 3;"

echo "Docker smoke passed."
