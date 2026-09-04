#!/bin/bash
# uniconv-Installer: richtet die Python-Umgebung ein und macht 'uniconv' überall aufrufbar.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$DIR/uniconv"

echo "1/2  Python-Umgebung einrichten …"
VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet pymupdf pymupdf4llm pillow pillow-heif markdown mammoth html2text

echo "2/3  Befehle 'uniconv' und 'uniconv-app' verfügbar machen …"
chmod +x "$DIR/uniconv-app" 2>/dev/null || true
LINKED=""
for BIN in /opt/homebrew/bin /usr/local/bin; do
    if [ -d "$BIN" ] && [ -w "$BIN" ]; then
        ln -sf "$DIR/uniconv" "$BIN/uniconv"
        [ -f "$DIR/uniconv-app" ] && ln -sf "$DIR/uniconv-app" "$BIN/uniconv-app"
        LINKED="$BIN/uniconv"
        break
    fi
done
if [ -z "$LINKED" ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$DIR/uniconv" "$HOME/.local/bin/uniconv"
    [ -f "$DIR/uniconv-app" ] && ln -sf "$DIR/uniconv-app" "$HOME/.local/bin/uniconv-app"
    LINKED="$HOME/.local/bin/uniconv"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) echo '   Hinweis: füge deiner ~/.zshrc hinzu:  export PATH="$HOME/.local/bin:$PATH"' ;;
    esac
fi

echo "3/3  Uniconv.app bauen …"
if [ -f "$DIR/uniconv_app.py" ]; then
    APP="$HOME/Applications/Uniconv.app"
    mkdir -p "$HOME/Applications"
    rm -rf "$APP"
    osacompile -o "$APP" -e "do shell script \"$DIR/uniconv-app\""
    if [ -f "$DIR/Uniconv.icns" ]; then
        cp "$DIR/Uniconv.icns" "$APP/Contents/Resources/applet.icns"
        rm -f "$APP/Contents/Resources/Assets.car"
        /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
    fi
    /usr/libexec/PlistBuddy -c "Set :CFBundleName Uniconv" "$APP/Contents/Info.plist" 2>/dev/null || true
    codesign --force -s - "$APP" 2>/dev/null || true
    touch "$APP"
    echo "   → $APP"
fi

echo
echo "Fertig! ($LINKED)"
echo "Terminal:  uniconv doctor        App:  open ~/Applications/Uniconv.app"
