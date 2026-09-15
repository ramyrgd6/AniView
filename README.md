<p align="center">
  <img src="assets/aniview.png" alt="AniView logo" width="180">
</p>

# AniView

AniView is an early-alpha desktop frontend for **ani-cli** and **mpv**. It gives
ani-cli a graphical interface with search, episode browsing, watch history,
recommendations, an embedded player, and a local-video library.

> **Current platform:** Fedora Linux. AniView currently embeds mpv through
> X11/XWayland. Windows support is planned, but is not part of this release.

## What AniView does

- Search by typing an anime title and pressing **Enter**
- Browse episodes in a side panel
- Play video inside the AniView window using mpv
- Resume episodes and keep Continue Watching history
- Show recently watched anime in a left sidebar
- Show popular/trending anime recommendations using AniList metadata
- Right-click Home/recent items for common history actions
- Scan user-selected folders and play local video files
- Toggle subtitles/dub mode and playback quality
- Use fullscreen and familiar media-player keyboard shortcuts

AniView does **not** host or upload video content.

## How it works

```text
AniView (PySide6 GUI)
├── ani-cli   → search and stream resolution
├── mpv       → video playback
└── AniList   → artwork and presentation metadata
```

AniView is an independent project. It is not affiliated with or endorsed by
mpv, ani-cli, AniList, or any content provider.

## Install on Fedora

### Requirements

- Fedora Linux
- Python 3.10+
- mpv
- XWayland
- Internet access for anime search/metadata

Make sure `mpv` is installed first. Then extract AniView and run:

```bash
chmod +x install.sh
./install.sh
```

The installer:

1. installs the Fedora Python/Qt and XWayland dependencies;
2. copies AniView to `~/.local/lib/aniview`;
3. downloads the current official ani-cli script from its upstream GitHub
   repository;
4. creates the `aniview` launcher and desktop-menu entry.

Launch with:

```bash
aniview
```

### Upgrade

Run the newer release's `install.sh`. Your history, settings, cached artwork,
and configured local-library folders are stored separately and are preserved.

## Search

The search field is intentionally just a search field. Type a title and press
**Enter**. There is no Search button or clickable search icon.

Press `/` or `Ctrl+F` to focus the search field from anywhere in the app.

## Local Library

AniView can scan folders you explicitly choose for common video formats,
including MKV, MP4, WebM, M4V, AVI, MOV, TS, and M2TS.

Local-library scanning is opt-in. AniView does not scan arbitrary folders on
your computer unless you add them.

## Keyboard controls

| Key | Action |
|---|---|
| `/` / `Ctrl+F` | Focus search |
| `H` | Home |
| `E` | Show/hide episode panel |
| `Space` / `K` | Play/pause |
| `J` | Back 10 seconds |
| `L` | Forward 10 seconds |
| `←` / `→` | Back/forward 5 seconds |
| `↑` / `↓` | Volume up/down |
| `F` / `F11` | Fullscreen |
| `Esc` | Exit fullscreen |
| `M` | Mute |
| `N` | Next episode |
| `P` | Previous episode |
| `0`–`9` | Jump to 0%–90% |

Playback shortcuts do not take over while you are typing in a text field.

## Local data

AniView keeps user data locally:

- settings/history/library folders: `~/.config/aniview/state.json`
- metadata/artwork/thumbnails/logs: `~/.cache/aniview/`

Uninstalling AniView does not automatically delete those folders.

## Troubleshooting

If video playback fails, check:

```bash
cat ~/.cache/aniview/mpv.log
```

If every anime search suddenly fails, ani-cli's upstream provider may have
changed. Re-running `install.sh` refreshes AniView's private ani-cli script.

## Development

AniView is currently a small Python/PySide6 project. See
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the project layout and local
checks.

Before opening a pull request, run:

```bash
bash scripts/check.sh
```

## Project status

**v0.5.3 is an alpha release.** The current goal is to stabilize the Fedora
experience and the UI before expanding platform support.

Planned work is tracked in [`ROADMAP.md`](ROADMAP.md). Windows support is a
future milestone.

## License and credits

AniView's own source code is released under the **MIT License**. See
[`LICENSE`](LICENSE).

AniView relies on third-party projects that keep their own licenses:

- [mpv](https://github.com/mpv-player/mpv) — playback engine
- [ani-cli](https://github.com/pystardust/ani-cli) — search/stream-resolution backend
- [AniList](https://anilist.co/) — artwork and presentation metadata

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for details.

The source repository does not include mpv or ani-cli. The Fedora installer
fetches ani-cli from its official upstream repository at install time.

## Content notice

AniView does not host, upload, or own the media that external software may
resolve. Users are responsible for complying with the laws and terms that
apply to them and to the sources they access.
