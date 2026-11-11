#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/dist/SQLTUI"
APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/sqltui"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
BIN_DIR="$HOME/.local/bin"

desktop_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}

desktop_path_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value// /\\s}"
    printf '%s' "$value"
}

if [[ ! -x "$SOURCE/SQLTUI" ]]; then
    printf 'SQLTUI bundle not found. Build it first with: .venv/bin/python packaging/build.py\n' >&2
    exit 1
fi

mkdir -p "$APP_ROOT" "$APPLICATIONS_DIR" "$ICONS_DIR" "$BIN_DIR"
cp -a "$SOURCE/." "$APP_ROOT/"
chmod +x "$APP_ROOT/SQLTUI"
cp "$APP_ROOT/sqltui.png" "$ICONS_DIR/sqltui.png"
ln -sfn "$APP_ROOT/SQLTUI" "$BIN_DIR/sqltui"

cat > "$APPLICATIONS_DIR/sqltui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SQLTUI
Comment=MySQL database workbench
Exec="$(desktop_escape "$BIN_DIR/sqltui")"
Icon=sqltui
Terminal=true
Categories=Development;Database;
StartupNotify=false
Path=$(desktop_path_escape "$APP_ROOT")
EOF
chmod 644 "$APPLICATIONS_DIR/sqltui.desktop"

printf 'Installed SQLTUI. Launch it from the application menu or run: %s/sqltui\n' "$BIN_DIR"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    printf 'Add %s to PATH to use the command from any terminal.\n' "$BIN_DIR"
fi
