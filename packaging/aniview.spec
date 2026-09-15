Name:           aniview
Version:        0.5.3
Release:        1%{?dist}
Summary:        Desktop frontend for ani-cli and mpv
License:        MIT AND GPL-3.0-or-later
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3-pyside6
Requires:       mpv
Requires:       xorg-x11-server-Xwayland
Requires:       curl

%description
AniView is a desktop frontend that uses ani-cli to resolve anime streams and
mpv for embedded playback. It provides search artwork, episode cards, local
watch history, continue watching, autoplay, resume, fullscreen controls and
YouTube-like keyboard shortcuts.

%prep
%autosetup

%build
# Pure Python / shell application; no compilation required.

%install
mkdir -p %{buildroot}%{_datadir}/aniview/helpers
mkdir -p %{buildroot}%{_datadir}/aniview/assets
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/512x512/apps

install -m 0755 aniview.py %{buildroot}%{_datadir}/aniview/aniview.py
install -m 0644 backend.py metadata.py mpv_controller.py state.py widgets.py %{buildroot}%{_datadir}/aniview/
install -m 0755 run.sh %{buildroot}%{_datadir}/aniview/run.sh
install -m 0755 ani-cli %{buildroot}%{_datadir}/aniview/ani-cli
install -m 0755 helpers/aniview-menu helpers/aniview-mpv-bridge %{buildroot}%{_datadir}/aniview/helpers/
install -m 0644 assets/*.svg %{buildroot}%{_datadir}/aniview/assets/
install -m 0644 assets/aniview.png %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/aniview.png

cat > %{buildroot}%{_bindir}/aniview <<'EOF'
#!/bin/sh
export QT_QPA_PLATFORM=xcb
export ANIVIEW_ANI_CLI=/usr/share/aniview/ani-cli
exec /usr/share/aniview/run.sh "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/aniview

cat > %{buildroot}%{_datadir}/applications/aniview.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=AniView
GenericName=Anime Frontend
Comment=Desktop frontend for ani-cli and mpv
Exec=aniview
Icon=aniview
Terminal=false
Categories=AudioVideo;Video;
Keywords=anime;mpv;video;ani-cli;
StartupNotify=true
EOF

%files
%license LICENSE ANI-CLI-LICENSE
%doc README.md THIRD_PARTY_NOTICES.md CHANGELOG.md ROADMAP.md
%{_bindir}/aniview
%{_datadir}/aniview/
%{_datadir}/applications/aniview.desktop
%{_datadir}/icons/hicolor/512x512/apps/aniview.png

%changelog
* Wed Sep 16 2026 AniView contributors - 0.5.3-1
- Enter-only search field and public GitHub release preparation
- Left navigation, recommendations, context menus, and local-file library

* Tue Sep 15 2026 AniView contributors - 0.2.0-1
- First RPM-packaged feature release
