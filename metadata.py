# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from state import APP_CACHE_DIR

ANILIST_ENDPOINT = "https://graphql.anilist.co"
META_CACHE_PATH = APP_CACHE_DIR / "metadata.json"
IMAGE_CACHE_DIR = APP_CACHE_DIR / "images"


ANILIST_RECOMMENDATIONS_QUERY = r"""
query {
  Page(page: 1, perPage: 14) {
    media(type: ANIME, isAdult: false, sort: [TRENDING_DESC, POPULARITY_DESC]) {
      id
      title { romaji english native }
      coverImage { extraLarge large medium color }
      bannerImage
      episodes
      duration
      seasonYear
      format
      status
      averageScore
      genres
    }
  }
}
"""

ANILIST_QUERY = r"""
query ($search: String!) {
  Page(page: 1, perPage: 1) {
    media(search: $search, type: ANIME, isAdult: false) {
      id
      title { romaji english native }
      coverImage { extraLarge large medium color }
      bannerImage
      episodes
      duration
      seasonYear
      format
      status
      averageScore
      genres
    }
  }
}
"""


class MetadataSignals(QObject):
    metadata_ready = Signal(str, object)
    image_ready = Signal(str, str)
    recommendations_ready = Signal(object)


class MetadataService:
    """Small AniList metadata/image cache used only for presentation."""

    def __init__(self) -> None:
        self.signals = MetadataSignals()
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache_lock = threading.Lock()
        self._inflight_meta: set[str] = set()
        self._meta_waiters: dict[str, list[str]] = {}
        self._inflight_images: set[str] = set()
        self._image_waiters: dict[str, list[str]] = {}
        self._net_sem = threading.Semaphore(4)
        self.cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

    @staticmethod
    def normalize(title: str) -> str:
        return " ".join(title.casefold().replace("_", " ").replace("-", " ").split())

    def _load_cache(self) -> None:
        try:
            if META_CACHE_PATH.exists():
                raw = json.loads(META_CACHE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.cache = raw
        except Exception:
            self.cache = {}

    def _save_cache(self) -> None:
        try:
            with self._cache_lock:
                snapshot = dict(self.cache)
            META_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            META_CACHE_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def cached(self, title: str) -> dict[str, Any] | None:
        data = self.cache.get(self.normalize(title))
        return dict(data) if data else None

    def fetch_async(self, title: str, token: str) -> None:
        cached = self.cached(title)
        if cached:
            self.signals.metadata_ready.emit(token, cached)
            return
        key = self.normalize(title)
        with self._cache_lock:
            if key in self._inflight_meta:
                self._meta_waiters.setdefault(key, []).append(token)
                return
            self._inflight_meta.add(key)
            self._meta_waiters[key] = [token]
        threading.Thread(target=self._fetch, args=(title, key), daemon=True).start()

    def _fetch(self, title: str, key: str) -> None:
        result: dict[str, Any] = {}
        try:
            payload = json.dumps({"query": ANILIST_QUERY, "variables": {"search": title}}).encode()
            req = urllib.request.Request(
                ANILIST_ENDPOINT,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "AniView/0.5.3",
                },
                method="POST",
            )
            with self._net_sem:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    doc = json.loads(resp.read().decode("utf-8", errors="replace"))
            media = (((doc.get("data") or {}).get("Page") or {}).get("media") or [])
            if media:
                item = media[0] or {}
                titles = item.get("title") or {}
                cover = item.get("coverImage") or {}
                result = {
                    "id": item.get("id"),
                    "title": titles.get("romaji") or titles.get("english") or title,
                    "english_title": titles.get("english"),
                    "native_title": titles.get("native"),
                    "cover_url": cover.get("extraLarge") or cover.get("large") or cover.get("medium"),
                    "banner_url": item.get("bannerImage"),
                    "accent": cover.get("color"),
                    "episodes": item.get("episodes"),
                    "duration": item.get("duration"),
                    "year": item.get("seasonYear"),
                    "format": item.get("format"),
                    "status": item.get("status"),
                    "score": item.get("averageScore"),
                    "genres": item.get("genres") or [],
                    "fetched": time.time(),
                }
                with self._cache_lock:
                    self.cache[self.normalize(title)] = result
                self._save_cache()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            result = {}
        finally:
            with self._cache_lock:
                self._inflight_meta.discard(key)
                waiters = self._meta_waiters.pop(key, [])
            for token in waiters:
                self.signals.metadata_ready.emit(token, result)

    def recommendations_async(self) -> None:
        threading.Thread(target=self._fetch_recommendations, daemon=True).start()

    def _fetch_recommendations(self) -> None:
        results: list[dict[str, Any]] = []
        try:
            payload = json.dumps({"query": ANILIST_RECOMMENDATIONS_QUERY}).encode()
            req = urllib.request.Request(
                ANILIST_ENDPOINT,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "AniView/0.5.3",
                },
                method="POST",
            )
            with self._net_sem:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    doc = json.loads(resp.read().decode("utf-8", errors="replace"))
            media = (((doc.get("data") or {}).get("Page") or {}).get("media") or [])
            for item in media:
                if not item:
                    continue
                titles = item.get("title") or {}
                cover = item.get("coverImage") or {}
                title = titles.get("english") or titles.get("romaji")
                if not title:
                    continue
                results.append({
                    "id": item.get("id"),
                    "title": titles.get("romaji") or title,
                    "english_title": titles.get("english"),
                    "native_title": titles.get("native"),
                    "cover_url": cover.get("extraLarge") or cover.get("large") or cover.get("medium"),
                    "banner_url": item.get("bannerImage"),
                    "accent": cover.get("color"),
                    "episodes": item.get("episodes"),
                    "duration": item.get("duration"),
                    "year": item.get("seasonYear"),
                    "format": item.get("format"),
                    "status": item.get("status"),
                    "score": item.get("averageScore"),
                    "genres": item.get("genres") or [],
                })
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            results = []
        self.signals.recommendations_ready.emit(results)

    def image_async(self, url: str | None, token: str) -> None:
        if not url:
            self.signals.image_ready.emit(token, "")
            return
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".img"
        path = IMAGE_CACHE_DIR / f"{hashlib.sha1(url.encode()).hexdigest()}{suffix}"
        if path.exists() and path.stat().st_size > 100:
            self.signals.image_ready.emit(token, str(path))
            return
        with self._cache_lock:
            if url in self._inflight_images:
                self._image_waiters.setdefault(url, []).append(token)
                return
            self._inflight_images.add(url)
            self._image_waiters[url] = [token]
        threading.Thread(target=self._image_fetch, args=(url, path), daemon=True).start()

    def _image_fetch(self, url: str, path: Path) -> None:
        final = ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AniView/0.5.3"})
            with self._net_sem:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read(8 * 1024 * 1024)
            if data:
                path.write_bytes(data)
                final = str(path)
        except (urllib.error.URLError, TimeoutError, OSError):
            final = ""
        finally:
            with self._cache_lock:
                self._inflight_images.discard(url)
                waiters = self._image_waiters.pop(url, [])
            for token in waiters:
                self.signals.image_ready.emit(token, final)
