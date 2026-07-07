#!/usr/bin/env bash
# 重启前后端开发服务。
#   后端: maestro/.venv 里的 uvicorn，:8000
#   前端: frontend 的 Vite dev server，:5173
# 日志写到项目根 logs/ 下，进程放后台运行。
#
# 用法:
#   ./restart.sh          重启前后端
#   ./restart.sh backend  只重启后端
#   ./restart.sh frontend 只重启前端
#   ./restart.sh stop     停掉前后端

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=5173

kill_port() {
  local port="$1" name="$2"
  local pids
  pids="$(lsof -ti "tcp:$port" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "停止 $name (端口 $port, pid: $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -ti "tcp:$port" 2>/dev/null || true)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}

start_backend() {
  kill_port "$BACKEND_PORT" "后端"
  echo "启动后端 → http://localhost:$BACKEND_PORT (日志: logs/backend.log)"
  cd "$ROOT/maestro"
  nohup .venv/bin/uvicorn maestro.main:app --reload --port "$BACKEND_PORT" \
    > "$LOG_DIR/backend.log" 2>&1 &
  cd "$ROOT"
}

start_frontend() {
  kill_port "$FRONTEND_PORT" "前端"
  echo "启动前端 → http://localhost:$FRONTEND_PORT (日志: logs/frontend.log)"
  cd "$ROOT/frontend"
  nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
  cd "$ROOT"
}

case "${1:-all}" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  stop)     kill_port "$BACKEND_PORT" "后端"; kill_port "$FRONTEND_PORT" "前端"; echo "已停止" ;;
  all)      start_backend; start_frontend ;;
  *)        echo "用法: $0 [all|backend|frontend|stop]"; exit 1 ;;
esac

if [ "${1:-all}" != "stop" ]; then
  echo ""
  echo "已在后台启动。查看日志:"
  echo "  tail -f logs/backend.log"
  echo "  tail -f logs/frontend.log"
fi
