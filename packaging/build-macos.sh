#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install -r requirements-desktop.txt

ICONSET="packaging/icons/app.iconset"
if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  SRC="packaging/icons/app.png"
  sips -z 16 16 "$SRC" --out "$ICONSET/icon_16x16.png" >/dev/null
  sips -z 32 32 "$SRC" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$SRC" --out "$ICONSET/icon_32x32.png" >/dev/null
  sips -z 64 64 "$SRC" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$SRC" --out "$ICONSET/icon_128x128.png" >/dev/null
  sips -z 256 256 "$SRC" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$SRC" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 512 512 "$SRC" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$SRC" --out "$ICONSET/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$SRC" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET" -o packaging/icons/app.icns
fi

python3 -m PyInstaller packaging/learning-loop.spec --noconfirm --clean
echo "Built dist/LearningLoop.app"
echo "Data is stored in ~/Library/Application Support/LearningLoop"
