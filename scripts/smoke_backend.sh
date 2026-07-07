#!/usr/bin/env bash
# G1 (mac/linux): frozen MaestroBackend boots to /health and serves a /chat.
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
  curl -sf "http://127.0.0.1:$PORT/health" > /tmp/maestro_smoke_health.json 2>/dev/null && break
  sleep 1
done
[ -s /tmp/maestro_smoke_health.json ] || {
  echo "FAIL: /health no response (60s)" >&2
  tail -20 /tmp/maestro_smoke.log >&2
  exit 1
}
echo "/health: $(cat /tmp/maestro_smoke_health.json)"

CHAT=$(curl -sf -X POST "http://127.0.0.1:$PORT/chat" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke","message":"你好"}' || true)
[ -n "$CHAT" ] || { echo "FAIL: /chat no response" >&2; exit 1; }
echo "/chat: $(printf '%s' "$CHAT" | head -c 200)"
echo "SMOKE OK"
