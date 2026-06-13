#!/usr/bin/env bash
# install_desktop.sh — Instala o atalho .desktop do IHS_INBOX no menu do usuário.
# Icon/StartupWMClass = "ihs-inbox" (casa com app.setDesktopFileName em main.py).
set -e
APP_DIR="$(dirname "$(readlink -f "$0")")"
ICON_SRC="$APP_DIR/logo.png"

# Copia o ícone pro tema XDG como ihs-inbox.png (casa com Icon=ihs-inbox).
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$ICON_DIR"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DIR/ihs-inbox.png"
fi

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/ihs-inbox.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=IHS INBOX
Comment=Arquivo de documentos de importação
Exec=$APP_DIR/iniciar.sh
Icon=ihs-inbox
Terminal=false
Categories=Office;Utility;
StartupWMClass=ihs-inbox
EOF

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "[IHS_INBOX] Atalho instalado: $DESKTOP_DIR/ihs-inbox.desktop"
