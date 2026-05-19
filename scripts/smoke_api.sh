#!/usr/bin/env bash
# Smoke-test a running InsightAI API (default http://localhost:8000).
set -euo pipefail

BASE_URL="${INSIGHTAI_SMOKE_URL:-http://localhost:8000}"
REQUIRE_LLM="${INSIGHTAI_SMOKE_REQUIRE_LLM:-false}"

echo "Smoke testing ${BASE_URL}"

echo "-> GET /api/v1/health"
curl -fsS "${BASE_URL}/api/v1/health" | tee /tmp/insightai-health.json
echo

echo "-> GET /api/v1/health/ready"
HTTP_READY="$(curl -s -o /tmp/insightai-ready.json -w '%{http_code}' "${BASE_URL}/api/v1/health/ready")"
cat /tmp/insightai-ready.json
echo
if [[ "${HTTP_READY}" != "200" && "${HTTP_READY}" != "503" ]]; then
  echo "Unexpected readiness status: ${HTTP_READY}" >&2
  exit 1
fi

if [[ "${REQUIRE_LLM}" == "true" ]]; then
  echo "-> POST /api/v1/ai/complete (live LLM)"
  curl -fsS -X POST "${BASE_URL}/api/v1/ai/complete" \
    -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"Reply with exactly: InsightAI OK"}]}' \
    | tee /tmp/insightai-complete.json
  echo
else
  echo "-> Skipping live LLM call (set INSIGHTAI_SMOKE_REQUIRE_LLM=true to enable)"
fi

echo "Smoke checks passed."
