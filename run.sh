#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# mpv's --wid embedding is an X11 model. On Fedora Wayland, AniView runs
# through XWayland so mpv can stay embedded inside the application window.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export ANIVIEW_ANI_CLI="${ANIVIEW_ANI_CLI:-$APP_DIR/ani-cli}"
exec python3 "$APP_DIR/aniview.py" "$@"
