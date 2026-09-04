#!/bin/bash
# uniconv-Installer (macOS): installiert das CLI per pipx und baut Uniconv.app.
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

echo "1/2  uniconv installieren (pipx) …"
pipx install --force $EDITABLE "$DIR"

PIPX_BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
APP_BIN="$PIPX_BIN/uniconv-app"
if [ ! -x "$APP_BIN" ]; then
    echo "Fehler: $APP_BIN wurde nicht angelegt." >&2
    exit 1
fi

FOUND="$(command -v uniconv 2>/dev/null || true)"
if [ -z "$FOUND" ]; then
    echo "   Hinweis: $PIPX_BIN ist nicht im PATH – einmal 'pipx ensurepath' ausführen und das Terminal neu öffnen."
elif [ "$FOUND" != "$PIPX_BIN/uniconv" ]; then
    echo "   Hinweis: 'uniconv' zeigt derzeit auf $FOUND (ältere Installation?) – ggf. entfernen."
fi

echo "2/2  Uniconv.app bauen …"
APP="$HOME/Applications/Uniconv.app"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
osacompile -o "$APP" -e "do shell script \"$APP_BIN\""
if [ -f "$DIR/assets/Uniconv.icns" ]; then
    cp "$DIR/assets/Uniconv.icns" "$APP/Contents/Resources/applet.icns"
    rm -f "$APP/Contents/Resources/Assets.car"
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
fi
/usr/libexec/PlistBuddy -c "Set :CFBundleName Uniconv" "$APP/Contents/Info.plist" 2>/dev/null || true
codesign --force -s - "$APP" 2>/dev/null || true
touch "$APP"
echo "   → $APP"

echo
echo "Fertig!   Terminal: uniconv doctor      App: open ~/Applications/Uniconv.app"
