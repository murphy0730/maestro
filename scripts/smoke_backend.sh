#!/usr/bin/env bash
# G1 (mac/linux): frozen MaestroBackend boots and accepts a Run.
# The unified Runtime exposes no /health route, so readiness is probed on GET /sessions.
# Run from repo root: ./scripts/smoke_backend.sh [path-to-MaestroBackend]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${1:-$ROOT/maestro/dist/backend/MaestroBackend}"
PORT="${MAESTRO_BACKEND_PORT:-9200}"
DATA="$(mktemp -d /tmp/maestro-smoke.XXXXXX)"

[ -x "$BACKEND" ] || { echo "frozen backend not found: $BACKEND" >&2; exit 2; }
echo "smoke: $BACKEND on :$PORT (data: $DATA)"

MAESTRO_DATA_DIR="$DATA" MAESTRO_BACKEND_PORT="$PORT" "$BACKEND" > /tmp/maestro_smoke.log 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; rm -rf "$DATA"; }
trap cleanup EXIT

# First onefolder run extracts to a cache and can be slow; allow 60s.
for i in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/sessions" > /tmp/maestro_smoke_ready.json 2>/dev/null && break
  sleep 1
done
[ -s /tmp/maestro_smoke_ready.json ] || {
  echo "FAIL: /sessions no response (60s)" >&2
  tail -20 /tmp/maestro_smoke.log >&2
  exit 1
}
echo "/sessions: $(head -c 200 /tmp/maestro_smoke_ready.json)"

# POST /runs answers 202 with the created Run; execution continues asynchronously and
# degrades gracefully without an LLM key, which is what CI runs with.
RUN=$(curl -sf -X POST "http://127.0.0.1:$PORT/runs" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke","message":"你好"}' || true)
[ -n "$RUN" ] || { echo "FAIL: POST /runs no response" >&2; tail -20 /tmp/maestro_smoke.log >&2; exit 1; }
printf '%s' "$RUN" | grep -q '"run_id"' || { echo "FAIL: POST /runs returned no run_id: $RUN" >&2; exit 1; }
echo "/runs: $(printf '%s' "$RUN" | head -c 200)"
echo "SMOKE OK"
