#!/usr/bin/env bash
# 重启前后端与 Electron 开发应用。
#   后端: maestro/.venv 里的 uvicorn，:8000
#   前端: frontend 的 Vite dev server，:5173
#   Electron: 复用 :5173，不另行启动 Vite
# 日志写到项目根 logs/ 下，进程放后台运行。
#
# 用法:
#   ./restart.sh          重启前后端与 Electron
#   ./restart.sh backend  只重启后端
#   ./restart.sh frontend 只重启前端
#   ./restart.sh electron 只重启 Electron
#   ./restart.sh stop     停掉前后端与 Electron

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=5173
ELECTRON_PID_FILE="$LOG_DIR/electron.pid"
DEV_PRIVILEGED_TOKEN="${PRIVILEGED_API_TOKEN:-maestro-local-dev}"

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
  # 用 python -m 绕开可能指向旧 worktree 的 uvicorn shebang；--app-dir 则确保
  # editable 安装残留旧路径时仍从当前仓库加载源码。
  PRIVILEGED_API_TOKEN="$DEV_PRIVILEGED_TOKEN" nohup .venv/bin/python -m uvicorn maestro.main:app --app-dir "$ROOT/maestro/src" --reload --port "$BACKEND_PORT" \
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

# start_electron 用绝对路径启动，所以这两个模式就是本项目 Electron 在 ps 里的样子:
#   wrapper: node <ROOT>/frontend/node_modules/.bin/electron .
#   实际应用: <ROOT>/frontend/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron
# 只匹配 wrapper 不够 —— 上次启动失败留下的孤儿应用进程会一直占着单实例锁,
# 让下一个实例刚起来就退出。两个模式都以 $ROOT 打头, 不会碰到别的项目。
ELECTRON_WRAPPER_PATTERN="$ROOT/frontend/node_modules/.bin/electron"
ELECTRON_APP_PATTERN="$ROOT/frontend/node_modules/electron/dist/"

electron_pids() {
  local pids=""
  if [ -f "$ELECTRON_PID_FILE" ]; then
    local saved_pid command_line
    saved_pid="$(cat "$ELECTRON_PID_FILE")"
    if [[ "$saved_pid" =~ ^[1-9][0-9]*$ ]]; then
      command_line="$(ps -p "$saved_pid" -o command= 2>/dev/null || true)"
      case "$command_line" in
        *"$ELECTRON_WRAPPER_PATTERN"*|*"$ELECTRON_APP_PATTERN"*) pids="$saved_pid" ;;
      esac
    fi
  fi
  if command -v pgrep >/dev/null 2>&1; then
    pids="$(printf '%s\n%s\n%s' "$pids" \
      "$(pgrep -f "$ELECTRON_WRAPPER_PATTERN" 2>/dev/null || true)" \
      "$(pgrep -f "$ELECTRON_APP_PATTERN" 2>/dev/null || true)")"
  fi
  printf '%s\n' "$pids" | awk '/^[1-9][0-9]*$/' | sort -u
}

stop_electron() {
  local pids
  pids="$(electron_pids)"
  if [ -n "$pids" ]; then
    echo "停止 Electron (pid: $(echo $pids))"
    kill $pids 2>/dev/null || true
    # 等进程真的退出: 单实例锁没释放的话, 新实例会立刻自杀。
    local waited=0
    while [ -n "$(electron_pids)" ] && [ "$waited" -lt 10 ]; do
      sleep 0.5
      waited=$((waited + 1))
    done
    pids="$(electron_pids)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
  rm -f "$ELECTRON_PID_FILE"
}

start_electron() {
  local electron_pid
  echo "等待前端就绪…"
  cd "$ROOT/frontend"
  ./node_modules/.bin/wait-on --timeout 30000 "tcp:127.0.0.1:$FRONTEND_PORT"
  echo "启动 Electron → http://127.0.0.1:$FRONTEND_PORT (日志: logs/electron.log)"
  # 绝对路径启动: ps 里就是绝对路径, stop_electron 的匹配才认得出自己起的进程。
  ELECTRON_RENDERER_URL="http://127.0.0.1:$FRONTEND_PORT" nohup "$ELECTRON_WRAPPER_PATTERN" . \
    > "$LOG_DIR/electron.log" 2>&1 &
  electron_pid=$!
  echo "$electron_pid" > "$ELECTRON_PID_FILE"
  sleep 1
  if ! kill -0 "$electron_pid" 2>/dev/null; then
    rm -f "$ELECTRON_PID_FILE"
    echo "Electron 启动失败，请查看 logs/electron.log" >&2
    return 1
  fi
  cd "$ROOT"
}

case "${1:-all}" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  electron) stop_electron; start_electron ;;
  stop)     stop_electron; kill_port "$BACKEND_PORT" "后端"; kill_port "$FRONTEND_PORT" "前端"; echo "已停止" ;;
  all)      stop_electron; start_backend; start_frontend; start_electron ;;
  *)        echo "用法: $0 [all|backend|frontend|electron|stop]"; exit 1 ;;
esac

if [ "${1:-all}" != "stop" ]; then
  echo ""
  echo "已在后台启动。查看日志:"
  echo "  tail -f logs/backend.log"
  echo "  tail -f logs/frontend.log"
  echo "  tail -f logs/electron.log"
fi
