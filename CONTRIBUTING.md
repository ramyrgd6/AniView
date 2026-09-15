# Contributing to AniView

Thanks for wanting to help.

AniView is still an early-alpha project, so small, focused changes are easiest
to review.

## Before changing code

1. Check existing GitHub issues first.
2. For a bug, include your Fedora version, desktop session (Wayland/X11), mpv version, and AniView version.
3. For a large feature or redesign, open an issue before doing a large amount of work.

## Local setup

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

Run the project checks before submitting a pull request:

```bash
bash scripts/check.sh
```

## Pull requests

A good pull request should:

- solve one clear problem;
- explain what changed and why;
- avoid unrelated formatting/refactoring;
- preserve existing user data when possible;
- include screenshots for visible UI changes;
- keep third-party attribution intact.

## Licensing

By submitting code to AniView, you agree that your contribution can be
released under AniView's MIT License.
