#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail

VERSION="0.5.3"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/lib/aniview"
BIN_DIR="$HOME/.local/bin"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_DIR="$XDG_DATA_HOME/applications"
ICON_DIR="$XDG_DATA_HOME/icons/hicolor/512x512/apps"
DOC_DIR="$INSTALL_DIR/docs"

printf '\nAniView %s installer\n=======================\n' "$VERSION"
printf 'Current target: Fedora Linux with X11/XWayland.\n\n'

if ! command -v dnf >/dev/null 2>&1; then
    echo "ERROR: This installer currently targets Fedora and requires dnf."
    echo "See README.md for development/manual-run information."
    exit 1
fi

if [ "${ANIVIEW_SKIP_DEPS:-0}" != "1" ]; then
    echo "Installing runtime dependencies..."
    sudo dnf install -y python3-pyside6 xorg-x11-server-Xwayland curl
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 was not found."
    exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("ERROR: AniView requires Python 3.10 or newer.")
PY

if ! command -v mpv >/dev/null 2>&1; then
    echo
    echo "ERROR: mpv was not found."
    echo "Install mpv from your configured Fedora/RPM Fusion repositories, then rerun this installer."
    exit 1
fi

mkdir -p "$INSTALL_DIR/helpers" "$INSTALL_DIR/assets" "$DOC_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
cp "$SRC_DIR"/*.py "$INSTALL_DIR/"
cp "$SRC_DIR/run.sh" "$INSTALL_DIR/"
cp "$SRC_DIR/helpers/aniview-menu" "$INSTALL_DIR/helpers/"
cp "$SRC_DIR/helpers/aniview-mpv-bridge" "$INSTALL_DIR/helpers/"
cp "$SRC_DIR/assets/"*.svg "$INSTALL_DIR/assets/" 2>/dev/null || true
cp "$SRC_DIR/assets/"*.png "$INSTALL_DIR/assets/" 2>/dev/null || true
cp "$SRC_DIR/LICENSE" "$DOC_DIR/LICENSE"
cp "$SRC_DIR/THIRD_PARTY_NOTICES.md" "$DOC_DIR/THIRD_PARTY_NOTICES.md"
chmod +x "$INSTALL_DIR/aniview.py" "$INSTALL_DIR/run.sh" "$INSTALL_DIR/helpers/"*

# AniView does not ship ani-cli in the source repository. The installer fetches
# the current upstream script from the official ani-cli repository at install time.
printf 'Fetching the current official ani-cli backend...\n'
tmp_ani_cli="$(mktemp)"
trap 'rm -f "$tmp_ani_cli"' EXIT
curl --proto '=https' --tlsv1.2 -fL \
    "https://raw.githubusercontent.com/pystardust/ani-cli/master/ani-cli" \
    -o "$tmp_ani_cli"
install -m 0755 "$tmp_ani_cli" "$INSTALL_DIR/ani-cli"

cat > "$BIN_DIR/aniview" <<LAUNCHER
#!/bin/sh
export QT_QPA_PLATFORM=xcb
export ANIVIEW_ANI_CLI="$INSTALL_DIR/ani-cli"
exec "$INSTALL_DIR/run.sh" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/aniview"

rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/aniview.svg"
cp "$SRC_DIR/assets/aniview.png" "$ICON_DIR/aniview.png"
cat > "$DESKTOP_DIR/aniview.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AniView
GenericName=Anime Frontend
Comment=Desktop frontend for ani-cli and mpv
Exec=$BIN_DIR/aniview
Icon=aniview
Terminal=false
Categories=AudioVideo;Video;
Keywords=anime;mpv;video;ani-cli;
StartupNotify=true
DESKTOP

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$XDG_DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
# KDE Plasma caches desktop entries separately. Rebuild that cache when available
# so upgrades do not keep showing AniView's previous icon.
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
command -v kbuildsycoca5 >/dev/null 2>&1 && kbuildsycoca5 --noincremental >/dev/null 2>&1 || true

printf '\nInstalled AniView %s.\n' "$VERSION"
printf 'Launch it from the app menu or run:\n\n  aniview\n\n'
printf 'Settings/history: ~/.config/aniview/state.json\n'
printf 'Cache/logs:       ~/.cache/aniview/\n'
