# AniView v0.5.3 — Alpha

This is the first GitHub-ready alpha of AniView.

## Highlights

- Plain Enter-to-search field with no Search button or clickable search icon
- Left navigation with recent anime
- Continue Watching and popular/trending recommendations
- Right-click history actions
- Episode browser with embedded mpv playback
- Resume, autoplay-next, fullscreen, and media shortcuts
- Local Library for user-selected video folders
- Fedora/XWayland installer
- Public-project documentation, third-party notices, issue templates, and CI checks

## Current limitations

- Fedora Linux is the current supported target
- Native Wayland and Windows player embedding are not implemented yet
- Anime search/playback depends on the external ani-cli project and its upstream provider
- Recommendations are popular/trending discovery results rather than personalized recommendations

## Install

Extract the release and run:

```bash
chmod +x install.sh
./install.sh
```

Then launch `aniview`.

See `README.md` for requirements and troubleshooting.

## Branding

- New AniView folded-ribbon play-mark logo.
- Transparent app icon used by the window, desktop launcher, and RPM package.
