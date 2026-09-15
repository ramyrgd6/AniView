# SPDX-License-Identifier: MIT
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import state


class AppStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        state.APP_CONFIG_DIR = root / "config"
        state.APP_CACHE_DIR = root / "cache"
        state.STATE_PATH = state.APP_CONFIG_DIR / "state.json"
        self.app = state.AppState()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_progress_is_saved_and_returned(self) -> None:
        self.app.update_progress(
            query="Example",
            index=1,
            title="Example Anime",
            episode="2",
            position=120,
            duration=1400,
            metadata={"year": 2026},
        )
        self.app.save()
        item = self.app.progress_for("Example Anime", "2")
        self.assertIsNotNone(item)
        self.assertEqual(item["episode"], "2")
        self.assertEqual(item["position"], 120.0)

    def test_recent_anime_deduplicates_titles(self) -> None:
        for ep in ("1", "2"):
            self.app.update_progress(
                query="Example",
                index=1,
                title="Example Anime",
                episode=ep,
                position=30,
                duration=1200,
            )
        recent = self.app.recent_anime()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["title"], "Example Anime")

    def test_library_folder_is_unique(self) -> None:
        folder = Path(self.tmp.name) / "anime"
        folder.mkdir()
        self.app.add_library_folder(str(folder))
        self.app.add_library_folder(str(folder))
        self.assertEqual(self.app.library_folders(), [str(folder.resolve())])


if __name__ == "__main__":
    unittest.main()
