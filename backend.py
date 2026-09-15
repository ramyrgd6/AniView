# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

APP_DIR = Path(__file__).resolve().parent
HELPER_DIR = APP_DIR / "helpers"
MENU_HELPER = HELPER_DIR / "aniview-menu"
BRIDGE_HELPER = HELPER_DIR / "aniview-mpv-bridge"
ANI_CLI = Path(os.environ.get("ANIVIEW_ANI_CLI", str(APP_DIR / "ani-cli")))
if not ANI_CLI.exists():
    found = shutil.which("ani-cli")
    ANI_CLI = Path(found) if found else ANI_CLI


class BackendSignals(QObject):
    search_done = Signal(object, str)
    episodes_done = Signal(object, str, int)
    stream_done = Signal(object, str, str)
    error = Signal(str)


class AniCliBackend:
    """Use ani-cli as the provider/resolver while AniView owns the GUI."""

    def __init__(self) -> None:
        self.signals = BackendSignals()

    def _base_env(self, temp_dir: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "ANI_CLI_MENU": str(MENU_HELPER),
                "ANI_CLI_PLAYER": str(BRIDGE_HELPER),
                "ANI_CLI_LOG": "0",
                "ANI_CLI_NO_DETACH": "1",
                "ANI_CLI_EXIT_AFTER_PLAY": "1",
                "ANIVIEW_CAPTURE_DIR": temp_dir,
                "ANIVIEW_BRIDGE_OUT": str(Path(temp_dir) / "bridge.bin"),
                "TERM": env.get("TERM", "xterm-256color"),
            }
        )
        return env

    def _run(self, args: list[str], temp_dir: str, timeout: int = 60) -> str:
        if not ANI_CLI.exists():
            raise RuntimeError("ani-cli was not found. Re-run the AniView installer to refresh its backend.")
        proc = subprocess.run(
            [str(ANI_CLI), *args],
            env=self._base_env(temp_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.stdout or ""

    @staticmethod
    def _read_capture(temp_dir: str) -> tuple[str, list[str]]:
        p = Path(temp_dir)
        prompt = (p / "prompt").read_text(errors="replace").strip() if (p / "prompt").exists() else ""
        items = (p / "items").read_text(errors="replace").splitlines() if (p / "items").exists() else []
        return prompt, [x.strip() for x in items if x.strip()]

    @staticmethod
    def _nice_error(output: str) -> str:
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
        lowered = plain.lower()
        if "blocked by cloudflare" in lowered:
            return "The anime provider was blocked by Cloudflare. Updating ani-cli or installing curl-impersonate may fix it."
        if "no results found" in lowered:
            return "No results found. If every search fails, refresh AniView's ani-cli backend."
        if "connection timed out" in lowered or "could not resolve host" in lowered:
            return "The provider could not be reached. Check your internet connection and try again."
        lines = [x.strip() for x in plain.splitlines() if x.strip()]
        return lines[-1] if lines else "ani-cli could not complete the request."

    def search_async(self, query: str) -> None:
        threading.Thread(target=self._search, args=(query,), daemon=True).start()

    def _search(self, query: str) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="aniview-search-") as td:
                output = self._run([query], td)
                prompt, items = self._read_capture(td)
                results: list[tuple[int, str]] = []
                if prompt.startswith("Select anime"):
                    for row in items:
                        m = re.match(r"^\s*(\d+)\s+(.*)$", row)
                        if m:
                            results.append((int(m.group(1)), m.group(2).strip()))
                elif prompt.startswith("Select episode"):
                    results = [(1, query)]
                elif (Path(td) / "bridge.bin").exists():
                    results = [(1, query)]
                if not results and "No results found" not in output:
                    raise RuntimeError(self._nice_error(output))
                self.signals.search_done.emit(results, query)
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def episodes_async(self, query: str, index: int, title: str, quality: str, dub: bool) -> None:
        threading.Thread(target=self._episodes, args=(query, index, title, quality, dub), daemon=True).start()

    def _episodes(self, query: str, index: int, title: str, quality: str, dub: bool) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="aniview-episodes-") as td:
                args = ["-S", str(index), "-q", quality]
                if dub:
                    args.append("--dub")
                args.append(query)
                output = self._run(args, td)
                prompt, items = self._read_capture(td)
                episodes: list[str] = []
                if prompt.startswith("Select episode"):
                    for row in items:
                        ep = row.strip().split()[0]
                        if re.match(r"^-?\d+(?:\.\d+)?$", ep):
                            episodes.append(ep)
                elif (Path(td) / "bridge.bin").exists():
                    episodes = ["1"]
                if not episodes:
                    raise RuntimeError(self._nice_error(output))
                self.signals.episodes_done.emit(episodes, title, index)
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def resolve_async(self, query: str, index: int, episode: str, title: str, quality: str, dub: bool) -> None:
        threading.Thread(
            target=self._resolve,
            args=(query, index, episode, title, quality, dub),
            daemon=True,
        ).start()

    def _resolve(self, query: str, index: int, episode: str, title: str, quality: str, dub: bool) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="aniview-resolve-") as td:
                args = ["-S", str(index), "-e", episode, "-q", quality, "--no-detach", "--exit-after-play"]
                if dub:
                    args.append("--dub")
                args.append(query)
                output = self._run(args, td, timeout=90)
                bridge = Path(td) / "bridge.bin"
                if not bridge.exists():
                    raise RuntimeError(self._nice_error(output))
                raw = bridge.read_bytes()
                argv = [x.decode(errors="replace") for x in raw.split(b"\0") if x]
                referrer = ""
                subtitle = ""
                media_title = f"{title} — Episode {episode}"
                url = ""
                for arg in argv:
                    if arg.startswith("--referrer="):
                        referrer = arg.split("=", 1)[1]
                    elif arg.startswith("--sub-file="):
                        subtitle = arg.split("=", 1)[1]
                    elif arg.startswith("--force-media-title="):
                        media_title = arg.split("=", 1)[1]
                    elif not arg.startswith("-"):
                        url = arg
                if not url:
                    raise RuntimeError("The episode resolved, but no video URL reached AniView.")
                self.signals.stream_done.emit(
                    {
                        "url": url,
                        "referrer": referrer,
                        "subtitle": subtitle,
                        "media_title": media_title,
                    },
                    title,
                    episode,
                )
        except Exception as exc:
            self.signals.error.emit(str(exc))
