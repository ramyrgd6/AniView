#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="0.5.3"
WORK="${TMPDIR:-/tmp}/aniview-rpm-$USER"
TOP="$WORK/rpmbuild"
SRC="$WORK/aniview-$VERSION"

if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "Installing Fedora RPM build tools..."
    sudo dnf install -y rpm-build curl
fi

rm -rf "$WORK"
mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$SRC"
cp -a "$ROOT"/. "$SRC"/
rm -rf "$SRC/.git" "$SRC/packaging"/*.rpm

# The normal installer also fetches current ani-cli. The RPM needs an offline
# copy inside the package, so fetch it while building the RPM.
echo "Fetching current ani-cli for the RPM payload..."
curl -fL https://raw.githubusercontent.com/pystardust/ani-cli/master/ani-cli -o "$SRC/ani-cli"
chmod +x "$SRC/ani-cli"

# Include ani-cli's GPL license alongside AniView's own MIT license.
curl -fL https://raw.githubusercontent.com/pystardust/ani-cli/master/LICENSE -o "$SRC/ANI-CLI-LICENSE"

tar -C "$WORK" -czf "$TOP/SOURCES/aniview-$VERSION.tar.gz" "aniview-$VERSION"
cp "$ROOT/packaging/aniview.spec" "$TOP/SPECS/aniview.spec"

rpmbuild --define "_topdir $TOP" -ba "$TOP/SPECS/aniview.spec"

mkdir -p "$ROOT/dist"
find "$TOP/RPMS" -name '*.rpm' -exec cp -v {} "$ROOT/dist/" \;
find "$TOP/SRPMS" -name '*.rpm' -exec cp -v {} "$ROOT/dist/" \;

echo
echo "RPM output: $ROOT/dist/"
