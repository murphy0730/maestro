#!/usr/bin/env bash
# 由 build/icon.svg 生成应用图标产物：build/icon.png (1024) 与 build/icon.icns。
# 产物会提交进仓库，只有改动 icon.svg 时才需要重跑。
#
# macOS 专用：依赖 Chrome headless 栅格化 + sips/iconutil 打包 icns。
# 用法: ./frontend/scripts/gen-app-icon.sh

set -euo pipefail
BUILD="$(cd "$(dirname "${BASH_SOURCE[0]}")/../build" && pwd)"
SRC="$BUILD/icon.svg"
PNG="$BUILD/icon.png"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

[ -f "$SRC" ] || { echo "错误: 未找到 $SRC" >&2; exit 1; }
[ -x "$CHROME" ] || { echo "错误: 未找到 Google Chrome，无法栅格化 SVG" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> [1/3] 栅格化 icon.svg → icon.png (1024×1024)"
# 包一层 margin:0 的 HTML，避免直接截 SVG 文档时受默认页边距影响导致偏移。
{
  printf '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:transparent}svg{display:block}</style>'
  cat "$SRC"
} > "$TMP/icon.html"

"$CHROME" --headless --disable-gpu --hide-scrollbars \
  --default-background-color=00000000 \
  --window-size=1024,1024 \
  --screenshot="$PNG" \
  "file://$TMP/icon.html" >/dev/null 2>&1

[ -f "$PNG" ] || { echo "错误: 截图未生成 $PNG" >&2; exit 1; }

echo "==> [2/3] 生成 iconset"
ICONSET="$TMP/icon.iconset"
mkdir -p "$ICONSET"
for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
            "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
            "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
  set -- $spec
  sips -z "$1" "$1" "$PNG" --out "$ICONSET/$2.png" >/dev/null
done

echo "==> [3/3] 打包 icns"
iconutil -c icns "$ICONSET" -o "$BUILD/icon.icns"

echo ""
echo "完成："
ls -la "$PNG" "$BUILD/icon.icns"
