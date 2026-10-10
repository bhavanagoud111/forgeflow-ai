#!/usr/bin/env bash
# Runs the JWT feature demo against a local API using curl and jq.
# Usage: FORGEFLOW_TOKEN=... ./examples/api/demo.sh
set -euo pipefail
BASE="${FORGEFLOW_URL:-http://localhost:8000}"
AUTH="Authorization: Bearer ${FORGEFLOW_TOKEN:?set FORGEFLOW_TOKEN}"

repo=$(curl -sf -H "$AUTH" "$BASE/api/repositories" | jq -r '.items[] | select(.full_name=="local/taskboard-api") | .id')
exec_id=$(curl -sf -H "$AUTH" -H 'Content-Type: application/json' "$BASE/api/executions" \
  -d "{\"repository_id\":\"$repo\",\"workflow\":\"feature\",\"request\":\"Add JWT authentication to this FastAPI application\"}" | jq -r .id)
echo "execution: $exec_id"

until status=$(curl -sf -H "$AUTH" "$BASE/api/executions/$exec_id" | jq -r .status) && \
      [[ "$status" =~ ^(awaiting_approval|succeeded|failed|blocked|rejected|cancelled)$ ]]; do sleep 1; done
echo "status: $status"
[[ "$status" == "awaiting_approval" ]] || exit 1

approval=$(curl -sf -H "$AUTH" "$BASE/api/executions/$exec_id" | jq -r .pending_approval_id)
curl -sf -H "$AUTH" -H 'Content-Type: application/json' "$BASE/api/approvals/$approval/approve" -d '{"comment":"demo"}' > /dev/null
until status=$(curl -sf -H "$AUTH" "$BASE/api/executions/$exec_id" | jq -r .status) && \
      [[ "$status" =~ ^(succeeded|failed|blocked|rejected|cancelled)$ ]]; do sleep 1; done
echo "final: $status"
curl -sf -H "$AUTH" "$BASE/api/executions/$exec_id/trace" | jq '.totals'
