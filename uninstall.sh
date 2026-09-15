#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
rm -rf "$HOME/.local/lib/aniview"
rm -f "$HOME/.local/bin/aniview"
rm -f "$HOME/.local/share/applications/aniview.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/aniview.svg"
rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/aniview.png"
echo "AniView application files removed."
echo "Watch history/settings were kept in ~/.config/aniview and cache in ~/.cache/aniview."
echo "Remove those directories manually if you also want to erase local AniView data."
