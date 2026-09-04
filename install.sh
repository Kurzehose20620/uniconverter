#!/bin/bash
# uniconverter-Installer (macOS): installiert das CLI per pipx und baut Uniconverter.app.
#   ./install.sh              normale Installation
#   ./install.sh --editable   Entwicklungsmodus: Codeänderungen sind sofort wirksam
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDITABLE=""
case "${1:-}" in
    -e|--editable) EDITABLE="--editable" ;;
esac

if ! command -v pipx >/dev/null 2>&1; then
    echo "pipx fehlt. Installation:  brew install pipx && pipx ensurepath" >&2
    exit 1
fi

echo "1/2  uniconverter installieren (pipx) …"
pipx install --force $EDITABLE "$DIR"

PIPX_BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
APP_BIN="$PIPX_BIN/uniconverter-app"
if [ ! -x "$APP_BIN" ]; then
    echo "Fehler: $APP_BIN wurde nicht angelegt." >&2
    exit 1
fi

FOUND="$(command -v uniconverter 2>/dev/null || true)"
if [ -z "$FOUND" ]; then
    echo "   Hinweis: $PIPX_BIN ist nicht im PATH – einmal 'pipx ensurepath' ausführen und das Terminal neu öffnen."
elif [ "$FOUND" != "$PIPX_BIN/uniconverter" ]; then
    echo "   Hinweis: 'uniconverter' zeigt derzeit auf $FOUND (ältere Installation?) – ggf. entfernen."
fi

echo "2/2  Uniconverter.app bauen …"
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
echo "Fertig!   Terminal: uniconverter doctor      App: open ~/Applications/Uniconverter.app"
