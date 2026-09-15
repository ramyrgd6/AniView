# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)


def _human_time(seconds: float | int | None) -> str:
    try:
        value = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        value = 0
    h, rem = divmod(value, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class ClickableFrame(QFrame):
    clicked = Signal()
    contextRequested = Signal(object)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.contextRequested.emit(event.globalPos())
        event.accept()


class CoverLabel(QLabel):
    """A QLabel that crops an image to fill its box."""

    def __init__(self, width: int = 120, height: int = 170, parent: QWidget | None = None):
        super().__init__(parent)
        self._source = QPixmap()
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignCenter)
        self.setText("▶")
        self.setObjectName("imagePlaceholder")

    def set_image(self, path: str | Path | None) -> None:
        pix = QPixmap(str(path)) if path else QPixmap()
        if pix.isNull():
            self._source = QPixmap()
            self.setPixmap(QPixmap())
            self.setText("▶")
            return
        self._source = pix
        self.setText("")
        self._rescale()

    def _rescale(self) -> None:
        if self._source.isNull() or self.width() < 2 or self.height() < 2:
            return
        scaled = self._source.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        self.setPixmap(scaled.copy(x, y, self.width(), self.height()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()


class SearchResultCard(ClickableFrame):
    activated = Signal(int, str)

    def __init__(self, index: int, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self.title = title
        self.metadata: dict[str, Any] = {}
        self.setObjectName("searchCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(178)
        self.clicked.connect(lambda: self.activated.emit(self.index, self.title))

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 16, 12)
        row.setSpacing(18)
        self.poster = CoverLabel(112, 158)
        row.addWidget(self.poster)

        text = QVBoxLayout()
        text.setContentsMargins(0, 3, 0, 2)
        text.setSpacing(7)
        self.title_label = QLabel(title, objectName="resultTitle")
        self.title_label.setWordWrap(True)
        text.addWidget(self.title_label)
        self.meta_label = QLabel("Anime", objectName="resultMeta")
        text.addWidget(self.meta_label)
        self.desc_label = QLabel("Select to view episodes", objectName="muted")
        self.desc_label.setWordWrap(True)
        text.addWidget(self.desc_label)
        text.addStretch(1)
        self.cta_label = QLabel("View episodes  →", objectName="resultCTA")
        text.addWidget(self.cta_label)
        row.addLayout(text, 1)

    def apply_metadata(self, data: dict[str, Any]) -> None:
        self.metadata = data or {}
        title = data.get("english_title") or data.get("title")
        if title:
            self.title_label.setText(title)
        pieces = []
        if data.get("year"):
            pieces.append(str(data["year"]))
        if data.get("format"):
            pieces.append(str(data["format"]).replace("_", " ").title())
        if data.get("episodes"):
            pieces.append(f"{data['episodes']} episodes")
        if data.get("score"):
            pieces.append(f"★ {int(data['score']) / 10:.1f}")
        if pieces:
            self.meta_label.setText("  •  ".join(pieces))
        genres = data.get("genres") or []
        if genres:
            self.desc_label.setText(" • ".join(str(x) for x in genres[:5]))


class EpisodeCard(QWidget):
    def __init__(self, episode: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.episode = str(episode)
        self.playing = False
        self.setObjectName("episodeCard")
        # Let QListWidget receive clicks even though the row has a custom widget.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(7, 7, 9, 7)
        row.setSpacing(10)

        self.thumb = CoverLabel(112, 63)
        row.addWidget(self.thumb)

        right = QVBoxLayout()
        right.setContentsMargins(0, 1, 0, 0)
        right.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title_label = QLabel(f"Episode {episode}", objectName="episodeTitle")
        title_row.addWidget(self.title_label, 1)
        self.playing_label = QLabel("PLAYING", objectName="playingLabel")
        self.playing_label.hide()
        title_row.addWidget(self.playing_label)
        right.addLayout(title_row)

        self.meta_label = QLabel("Ready to play", objectName="episodeMeta")
        right.addWidget(self.meta_label)
        right.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        right.addWidget(self.progress)
        row.addLayout(right, 1)

    def set_playing(self, playing: bool) -> None:
        self.playing = playing
        self.playing_label.setVisible(playing)
        self.setProperty("playing", playing)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_progress(self, position: float, duration: float, finished: bool = False) -> None:
        position = max(0.0, float(position or 0))
        duration = max(0.0, float(duration or 0))
        if finished:
            self.progress.setValue(1000)
            self.progress.show()
            self.meta_label.setText("Watched")
            self.setProperty("watched", True)
        elif duration > 0 and position > 2:
            pct = max(0, min(1000, int(position / duration * 1000)))
            self.progress.setValue(pct)
            self.progress.show()
            remaining = max(0, duration - position)
            self.meta_label.setText(f"{_human_time(position)} watched  •  {_human_time(remaining)} left")
            self.setProperty("watched", False)
        else:
            self.progress.hide()
            self.meta_label.setText("Ready to play")
            self.setProperty("watched", False)
        self.style().unpolish(self)
        self.style().polish(self)


class HomeCard(ClickableFrame):
    activated = Signal(object)

    def __init__(self, entry: dict[str, Any], show_progress: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("homeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(260)
        self.clicked.connect(lambda: self.activated.emit(self.entry))

        col = QVBoxLayout(self)
        col.setContentsMargins(6, 6, 6, 9)
        col.setSpacing(7)
        self.poster = CoverLabel(248, 140)
        col.addWidget(self.poster)

        title = QLabel(str(entry.get("title") or "Unknown"), objectName="homeTitle")
        title.setWordWrap(True)
        title.setMaximumHeight(42)
        col.addWidget(title)

        ep_num = entry.get("episode", "?")
        meta_text = f"Episode {ep_num}"
        duration = float(entry.get("duration") or 0)
        position = float(entry.get("position") or 0)
        if show_progress and duration > 0:
            remaining = max(0, duration - position)
            meta_text += f"  •  {_human_time(remaining)} left"
        self.meta_label = QLabel(meta_text, objectName="homeMeta")
        col.addWidget(self.meta_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(4)
        if show_progress and duration > 0:
            self.progress.setValue(max(0, min(1000, int(position / duration * 1000))))
            col.addWidget(self.progress)
        col.addStretch(1)


class RecommendationCard(ClickableFrame):
    activated = Signal(str)

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.data = dict(data or {})
        self.title = str(self.data.get("english_title") or self.data.get("title") or "Unknown")
        self.setObjectName("recommendationCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(188)
        self.clicked.connect(lambda: self.activated.emit(self.title))

        col = QVBoxLayout(self)
        col.setContentsMargins(5, 5, 5, 8)
        col.setSpacing(7)
        self.poster = CoverLabel(178, 250)
        col.addWidget(self.poster)
        self.title_label = QLabel(self.title, objectName="recommendationTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(42)
        col.addWidget(self.title_label)

        meta = []
        if self.data.get("year"):
            meta.append(str(self.data["year"]))
        if self.data.get("format"):
            meta.append(str(self.data["format"]).replace("_", " ").title())
        if self.data.get("score"):
            meta.append(f"★ {int(self.data['score']) / 10:.1f}")
        self.meta_label = QLabel("  •  ".join(meta) or "Anime", objectName="homeMeta")
        col.addWidget(self.meta_label)
        col.addStretch(1)


class LocalFileCard(ClickableFrame):
    activated = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = str(path)
        p = Path(path)
        self.setObjectName("localFileCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(72)
        self.clicked.connect(lambda: self.activated.emit(self.path))

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 14, 10)
        row.setSpacing(12)
        badge = QLabel("▶", objectName="localPlayBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(44, 44)
        row.addWidget(badge)

        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel(p.stem, objectName="localTitle")
        title.setWordWrap(True)
        text.addWidget(title)
        try:
            size = p.stat().st_size
            if size >= 1024 ** 3:
                size_text = f"{size / (1024 ** 3):.1f} GB"
            elif size >= 1024 ** 2:
                size_text = f"{size / (1024 ** 2):.0f} MB"
            else:
                size_text = f"{size / 1024:.0f} KB"
        except OSError:
            size_text = "Video file"
        meta = QLabel(f"{p.parent}  •  {size_text}", objectName="localMeta")
        meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text.addWidget(meta)
        row.addLayout(text, 1)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("AniView Settings")
        self.setModal(True)
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 20)
        form.setSpacing(15)

        self.quality = QComboBox()
        self.quality.addItems(["best", "1080", "720", "480", "360"])
        self.quality.setCurrentText(str(settings.get("quality", "best")))
        form.addRow("Default quality", self.quality)

        self.language = QComboBox()
        self.language.addItems(["SUB", "DUB"])
        self.language.setCurrentText("DUB" if settings.get("dub") else "SUB")
        form.addRow("Default audio", self.language)

        self.autoplay = QCheckBox("Play the next episode automatically")
        self.autoplay.setChecked(bool(settings.get("autoplay_next", True)))
        form.addRow("Autoplay", self.autoplay)

        self.resume = QCheckBox("Resume episodes where I left off")
        self.resume.setChecked(bool(settings.get("resume_playback", True)))
        form.addRow("Resume", self.resume)

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 130)
        self.volume.setValue(int(settings.get("volume", 100)))
        form.addRow("Default volume", self.volume)

        self.theme = QComboBox()
        self.theme.addItems(["Dark", "Dim", "Light"])
        self.theme.setCurrentText(str(settings.get("theme", "Dark")))
        form.addRow("Theme", self.theme)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_btn = buttons.button(QDialogButtonBox.Save)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if save_btn is not None:
            save_btn.setObjectName("primaryButton")
            save_btn.setText("Save")
            icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
            save_btn.setIcon(icon)
        if cancel_btn is not None:
            cancel_btn.setObjectName("secondaryButton")
            cancel_btn.setText("Cancel")
            icon = self.style().standardIcon(QStyle.SP_DialogCancelButton)
            cancel_btn.setIcon(icon)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def values(self) -> dict[str, Any]:
        return {
            "quality": self.quality.currentText(),
            "dub": self.language.currentText() == "DUB",
            "autoplay_next": self.autoplay.isChecked(),
            "resume_playback": self.resume.isChecked(),
            "volume": self.volume.value(),
            "theme": self.theme.currentText(),
        }
