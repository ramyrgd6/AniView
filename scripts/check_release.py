#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "0.5.3"

required = [
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "ROADMAP.md",
    ".gitignore",
    "install.sh",
    "run.sh",
    "uninstall.sh",
    "aniview.py",
    "backend.py",
    "metadata.py",
    "mpv_controller.py",
    "state.py",
    "widgets.py",
]

missing = [name for name in required if not (ROOT / name).exists()]
if missing:
    raise SystemExit("Missing release files: " + ", ".join(missing))

checks = {
    "aniview.py": r'APP_VERSION\s*=\s*"([^"]+)"',
    "packaging/build-rpm.sh": r'VERSION="([^"]+)"',
    "packaging/aniview.spec": r'^Version:\s*([^\s]+)',
}

for rel, pattern in checks.items():
    text = (ROOT / rel).read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find version in {rel}")
    if match.group(1) != EXPECTED:
        raise SystemExit(f"Version mismatch in {rel}: {match.group(1)} != {EXPECTED}")

metadata = (ROOT / "metadata.py").read_text(encoding="utf-8")
if f"AniView/{EXPECTED}" not in metadata:
    raise SystemExit("metadata.py User-Agent version is not current")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
if "**Enter**" not in readme or "There is no Search button" not in readme:
    raise SystemExit("README must document Enter-only search")

app = (ROOT / "aniview.py").read_text(encoding="utf-8")
for forbidden in ("self.search_action", 'self.search.setClearButtonEnabled(True)'):
    if forbidden in app:
        raise SystemExit(f"Search UI still contains forbidden release pattern: {forbidden}")

print(f"AniView {EXPECTED} release metadata looks consistent.")
