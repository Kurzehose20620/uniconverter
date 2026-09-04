#!/bin/bash
# uniconverter installer (macOS): installs the CLI via pipx and builds Uniconverter.app.
#   ./install.sh              normal installation
#   ./install.sh --editable   development mode: code changes take effect immediately
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDITABLE=""
case "${1:-}" in
    -e|--editable) EDITABLE="--editable" ;;
esac

if ! command -v pipx >/dev/null 2>&1; then
    echo "pipx is missing. Install it with:  brew install pipx && pipx ensurepath" >&2
    exit 1
fi

echo "1/2  Installing uniconverter (pipx) …"
pipx install --force $EDITABLE "$DIR"

PIPX_BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
APP_BIN="$PIPX_BIN/uniconverter-app"
if [ ! -x "$APP_BIN" ]; then
    echo "Error: $APP_BIN was not created." >&2
    exit 1
fi

FOUND="$(command -v uniconverter 2>/dev/null || true)"
if [ -z "$FOUND" ]; then
    echo "   Note: $PIPX_BIN is not in your PATH – run 'pipx ensurepath' once and reopen the terminal."
elif [ "$FOUND" != "$PIPX_BIN/uniconverter" ]; then
    echo "   Note: 'uniconverter' currently resolves to $FOUND (older installation?) – remove it if unwanted."
fi

echo "2/2  Building Uniconverter.app …"
VERSION="$("$APP_BIN" --version | awk '{print $2}')"
APP="$HOME/Applications/Uniconverter.app"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/Uniconverter" <<EOF
#!/bin/bash
exec "$APP_BIN"
EOF
chmod +x "$APP/Contents/MacOS/Uniconverter"
cp "$DIR/src/uniconverter/Uniconverter.icns" "$APP/Contents/Resources/Uniconverter.icns"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Uniconverter</string>
  <key>CFBundleDisplayName</key><string>Uniconverter</string>
  <key>CFBundleIdentifier</key><string>de.leonbrzosa.uniconverter</string>
  <key>CFBundleVersion</key><string>${VERSION:-0}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION:-0}</string>
  <key>CFBundleExecutable</key><string>Uniconverter</string>
  <key>CFBundleIconFile</key><string>Uniconverter</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
EOF
codesign --force -s - "$APP" 2>/dev/null || true
touch "$APP"
echo "   → $APP"

echo
echo "Done!   Terminal: uniconverter doctor      App: open ~/Applications/Uniconverter.app"
