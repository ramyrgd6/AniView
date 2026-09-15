#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/4] Python syntax"
python3 -m compileall -q aniview.py backend.py metadata.py mpv_controller.py state.py widgets.py scripts tests

echo "[2/4] Shell syntax"
bash -n install.sh
bash -n packaging/build-rpm.sh
sh -n run.sh
sh -n uninstall.sh
sh -n helpers/aniview-menu
sh -n helpers/aniview-mpv-bridge

echo "[3/4] Unit tests"
python3 -m unittest discover -s tests -v

echo "[4/4] Release metadata"
python3 scripts/check_release.py

echo
echo "All non-GUI checks passed."
