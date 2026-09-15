# Third-Party Notices

AniView is an independent project and is not affiliated with or endorsed by
the projects or services listed below.

## mpv

Project: <https://github.com/mpv-player/mpv>

AniView launches mpv as a separate playback process and embeds its video output
inside the AniView window. AniView does not include mpv in this source
repository.

mpv is normally distributed under **GPL-2.0-or-later**; mpv can also be built
under **LGPL-2.1-or-later** when configured without GPL-only components. Refer
to the mpv project for the license terms of the mpv build installed on your
system.

## ani-cli

Project: <https://github.com/pystardust/ani-cli>

AniView uses ani-cli as an external search and stream-resolution backend.
ani-cli is licensed under **GPL-3.0-or-later**.

The AniView source repository does not contain ani-cli. `install.sh` downloads
the current official ani-cli script from the upstream repository at install
time. The optional RPM build helper may fetch and package ani-cli; when it does,
ani-cli's GPL license is included in that package.

## AniList

Service: <https://anilist.co/>
API: <https://graphql.anilist.co/>

AniView uses AniList's API for presentation metadata such as titles, cover art,
year, format, genres, scores, and popular/trending recommendations. AniList is
not involved in AniView video playback.

Metadata and artwork remain subject to the rights and terms that apply to their
respective owners/services.

## Media

AniView does not host, upload, or claim ownership of video content. Playback
sources resolved by external software remain subject to the terms, rights, and
laws that apply to the user and source.
