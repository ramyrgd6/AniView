# Releasing AniView on GitHub

This is the simple release process for the current alpha.

## First public repository setup

1. Create a new public GitHub repository named `AniView` (or `aniview`).
2. Upload/push the contents of this project folder, not the outer ZIP file.
3. Keep `LICENSE`, `README.md`, and `THIRD_PARTY_NOTICES.md` in the repository root.
4. In the repository About section, a suitable description is:

   **Desktop frontend for ani-cli and mpv with search, history, recommendations, and a local video library.**

5. Enable **Issues**. GitHub will automatically use the included bug/feature templates.
6. If available, enable **Private vulnerability reporting** under repository security settings.

## Before creating a release

Run:

```bash
bash scripts/check.sh
```

Then manually verify:

- the app installs on a clean/reasonably clean Fedora environment;
- search works by typing a title and pressing Enter;
- at least one episode resolves and plays;
- episode sidebar hides and reopens;
- fullscreen enters and exits;
- Continue Watching works after restarting;
- Local Library can add a folder and play a local file;
- no passwords, account tokens, local absolute paths, or personal files are committed.

## GitHub release

For this source version:

- Tag: `v0.5.3`
- Title: `AniView v0.5.3 — Alpha`
- Mark it as a **pre-release** because AniView is still alpha software.

Suggested release notes:

> First public alpha of AniView. Fedora/XWayland is the current supported target.
> AniView provides a desktop interface around ani-cli and mpv, with episode
> browsing, watch history, recommendations, and a local-video library.
>
> See README.md for installation requirements and known platform limitations.

GitHub automatically provides source `.zip` and `.tar.gz` downloads for a tag,
so you do not have to upload another source archive unless you want to.

## Screenshots

Before announcing the repository widely, add a few current screenshots to a
`docs/screenshots/` folder and place them near the top of the README:

- Home
- Search results
- Watch page
- Local Library

Do not use screenshots from an older design.
