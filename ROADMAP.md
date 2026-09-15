# AniView Roadmap

This is a direction document, not a promise of dates.

## Current: stabilize the Fedora alpha

- Fix playback/provider regressions without redesigning the whole UI.
- Improve accessibility, keyboard navigation, loading/error states, and reliability.
- Collect real-world Fedora/XWayland bug reports.
- Add screenshots and a short demo to the GitHub project page.

## Next

- Improve Local Library organization and filename parsing.
- Add better history/library management.
- Make recommendation behavior more useful while keeping it understandable.
- Explore safe, legitimate offline-download integrations where the source explicitly permits downloads.

## Future platform work

- **Windows support** using a native Win32 mpv embedding path.
- Broader Linux distribution support.
- Consider a native Wayland/libmpv path if the architecture becomes mature enough.

The goal is one AniView codebase with platform-specific playback integration,
not separate unrelated apps for every operating system.
