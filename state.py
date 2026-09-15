# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

APP_CONFIG_DIR = Path.home() / ".config" / "aniview"
APP_CACHE_DIR = Path.home() / ".cache" / "aniview"
STATE_PATH = APP_CONFIG_DIR / "state.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "quality": "best",
    "dub": False,
    "autoplay_next": True,
    "resume_playback": True,
    "volume": 100,
    "theme": "Dark",
    "library_folders": [],
}


class AppState:
    def __init__(self) -> None:
        APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "version": 2,
            "settings": dict(DEFAULT_SETTINGS),
            "history": {},
        }
        self.load()

    @property
    def settings(self) -> dict[str, Any]:
        return self.data.setdefault("settings", dict(DEFAULT_SETTINGS))

    @property
    def history(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("history", {})

    def load(self) -> None:
        if not STATE_PATH.exists():
            return
        try:
            loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
                settings = dict(DEFAULT_SETTINGS)
                settings.update(self.data.get("settings") or {})
                self.data["settings"] = settings
                if not isinstance(self.data.get("history"), dict):
                    self.data["history"] = {}
        except Exception:
            # A broken state file should never prevent the player from opening.
            pass

    def save(self) -> None:
        APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=APP_CONFIG_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(temp_name, STATE_PATH)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

    @staticmethod
    def episode_key(title: str, episode: str) -> str:
        return f"{title.strip().casefold()}::{str(episode).strip()}"

    def progress_for(self, title: str, episode: str) -> dict[str, Any] | None:
        return self.history.get(self.episode_key(title, episode))

    def update_progress(
        self,
        *,
        query: str,
        index: int,
        title: str,
        episode: str,
        position: float,
        duration: float,
        metadata: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> dict[str, Any]:
        key = self.episode_key(title, episode)
        old = self.history.get(key, {})
        entry: dict[str, Any] = {
            **old,
            "query": query,
            "index": int(index),
            "title": title,
            "episode": str(episode),
            "position": max(0.0, float(position or 0)),
            "duration": max(0.0, float(duration or 0)),
            "finished": bool(finished),
            "updated": time.time(),
        }
        if metadata:
            entry["metadata"] = {
                k: metadata.get(k)
                for k in (
                    "id",
                    "title",
                    "english_title",
                    "cover_url",
                    "banner_url",
                    "year",
                    "format",
                    "episodes",
                    "duration",
                )
                if metadata.get(k) is not None
            }
        self.history[key] = entry

        # Keep state compact. 300 episodes is far more than the home screen needs.
        if len(self.history) > 300:
            ordered = sorted(self.history.items(), key=lambda kv: kv[1].get("updated", 0), reverse=True)
            self.data["history"] = dict(ordered[:300])
        return entry

    def continue_watching(self, limit: int = 10) -> list[dict[str, Any]]:
        entries = []
        for item in self.history.values():
            duration = float(item.get("duration") or 0)
            position = float(item.get("position") or 0)
            if item.get("finished"):
                continue
            if position < 10:
                continue
            if duration > 0 and position >= max(0, duration - 45):
                continue
            entries.append(item)
        entries.sort(key=lambda x: x.get("updated", 0), reverse=True)
        return entries[:limit]

    def recent_anime(self, limit: int = 12) -> list[dict[str, Any]]:
        ordered = sorted(self.history.values(), key=lambda x: x.get("updated", 0), reverse=True)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in ordered:
            key = str(item.get("title", "")).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(item)
            if len(result) >= limit:
                break
        return result


    def remove_title(self, title: str) -> None:
        key = title.strip().casefold()
        self.data["history"] = {
            k: v for k, v in self.history.items()
            if str(v.get("title", "")).strip().casefold() != key
        }
        self.save()

    def mark_title_watched(self, title: str, watched: bool = True) -> None:
        key = title.strip().casefold()
        now = time.time()
        for item in self.history.values():
            if str(item.get("title", "")).strip().casefold() == key:
                item["finished"] = bool(watched)
                if watched and float(item.get("duration") or 0) > 0:
                    item["position"] = float(item.get("duration") or 0)
                elif not watched:
                    item["finished"] = False
                    item["position"] = 0.0
                item["updated"] = now
        self.save()

    def add_library_folder(self, folder: str) -> None:
        folders = self.settings.setdefault("library_folders", [])
        normalized = str(Path(folder).expanduser().resolve())
        if normalized not in folders:
            folders.append(normalized)
            self.save()

    def remove_library_folder(self, folder: str) -> None:
        normalized = str(Path(folder).expanduser().resolve())
        folders = self.settings.setdefault("library_folders", [])
        self.settings["library_folders"] = [x for x in folders if str(x) != normalized]
        self.save()

    def library_folders(self) -> list[str]:
        values = self.settings.get("library_folders") or []
        return [str(x) for x in values if str(x).strip()]

    def clear_history(self) -> None:
        self.data["history"] = {}
        self.save()
