# Development

AniView is currently a small Python/PySide6 application rather than a large
framework-based project.

## Main files

- `aniview.py` — main window, navigation, player UI, shortcuts, and app flow
- `widgets.py` — reusable cards/dialog widgets
- `backend.py` — talks to ani-cli through small helper scripts
- `mpv_controller.py` — starts and controls the embedded mpv process
- `metadata.py` — AniList metadata/artwork cache
- `state.py` — settings, history, and Local Library folder state
- `helpers/` — tiny shell adapters used when talking to ani-cli
- `assets/` — app/UI SVG assets

## Runtime model

AniView currently targets Fedora and runs the Qt interface through XWayland.
The mpv controller embeds mpv using an X11 window ID.

That is why Windows and native Wayland support require platform-specific work
instead of only changing the installer.

## Running from the source tree

Install the required system programs first:

- Python 3.10+
- PySide6
- mpv
- XWayland
- ani-cli

Then set the ani-cli path and run:

```bash
export QT_QPA_PLATFORM=xcb
export ANIVIEW_ANI_CLI="$(command -v ani-cli)"
python3 aniview.py
```

The normal Fedora `install.sh` downloads a private current copy of ani-cli, so
regular users do not need to perform this manual setup.

## Checks

Run:

```bash
bash scripts/check.sh
```

This checks Python syntax, shell syntax, basic state tests, version consistency,
and required release files. It does not replace actual GUI/playback testing.

## UI changes

For visible changes, test at minimum:

1. Home
2. Search results
3. Watch page with episode sidebar open and closed
4. Fullscreen enter/exit
5. Settings dialog
6. Local Library

Include screenshots with pull requests that change the UI.
