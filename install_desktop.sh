#!/usr/bin/env bash
# install_desktop.sh — Instala o atalho .desktop do IHS_INBOX no menu do usuário.
# Icon/StartupWMClass = "ihs-inbox" (casa com app.setDesktopFileName em main.py).
set -e
APP_DIR="$(dirname "$(readlink -f "$0")")"
ICON_SRC="$APP_DIR/logo.png"

# Copia o ícone pro tema XDG como ihs-inbox.png (reforço; casaria com Icon=ihs-inbox).
# Obs.: logo.png é 1024x1024. Pôr ele numa pasta "256x256" funciona no Ubuntu, mas
# o Pop!_OS é mais rígido e rejeita o ícone por causa do tamanho que não bate.
# Por isso o .desktop abaixo aponta o Icon pro CAMINHO ABSOLUTO do arquivo, que
# ignora tema/cache/pasta-por-tamanho e funciona em qualquer distro.
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
Icon=$ICON_SRC
Terminal=false
Categories=Office;Utility;
StartupWMClass=ihs-inbox
EOF

# Atualiza os caches (o Pop!_OS depende deles; o Ubuntu releva).
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "[IHS_INBOX] Atalho instalado: $DESKTOP_DIR/ihs-inbox.desktop"
