#!/usr/bin/env bash
# 一键打包 macOS 版 Electron 应用 (arm64 .dmg)。
# 全链: 冻结后端 (PyInstaller) → 打包前端+Electron (electron-builder)。
# 产物: frontend/release/*.dmg
#
# 注意: 打包链里的后端是 PyInstaller 原生二进制，无法跨平台编译。
#       本脚本只产 macOS 包；Windows 包请在 Windows 上跑 build-win.bat。
#
# 用法: ./build-mac.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT/maestro/.venv/bin/python"

echo "==> [1/4] 检查后端 venv"
if [ ! -x "$VENV_PY" ]; then
  echo "错误: 未找到 $VENV_PY" >&2
  echo "请先创建后端环境: cd maestro && uv venv --python 3.12 && uv pip install -e \".[dev]\"" >&2
  exit 1
fi

echo "==> [2/4] 确保 PyInstaller 已安装"
if ! "$VENV_PY" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller 缺失，安装 maestro[packaging] ..."
  "$VENV_PY" -m pip install -e "$ROOT/maestro[packaging]"
fi

echo "==> [3/4] 冻结后端 → maestro/dist/backend/"
cd "$ROOT/maestro"
"$VENV_PY" -m PyInstaller maestro_backend.spec --noconfirm
if [ ! -x "$ROOT/maestro/dist/backend/MaestroBackend" ]; then
  echo "错误: 冻结产物 maestro/dist/backend/MaestroBackend 未生成" >&2
  exit 1
fi

echo "==> [4/4] 打包 Electron (vite build + electron-builder)"
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run electron:build

echo ""
echo "完成。产物在 frontend/release/:"
ls -1 "$ROOT/frontend/release" 2>/dev/null | grep -Ei '\.dmg$' || echo "  (未找到 .dmg，检查 electron-builder 输出)"
