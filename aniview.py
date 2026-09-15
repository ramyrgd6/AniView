#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QSize,
    QVariantAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QCursor, QIcon, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend import AniCliBackend
from metadata import MetadataService
from mpv_controller import MPVController
from state import APP_CACHE_DIR, AppState
from widgets import (
    CoverLabel,
    EpisodeCard,
    HomeCard,
    LocalFileCard,
    RecommendationCard,
    SearchResultCard,
    SettingsDialog,
)

APP_NAME = "AniView"
APP_VERSION = "0.5.3"


THEMES: dict[str, dict[str, str]] = {
    "Dark": {
        "bg": "#0f0f0f",
        "panel": "#181818",
        "panel2": "#272727",
        "hover": "#353535",
        "text": "#f1f1f1",
        "muted": "#aaaaaa",
        "border": "#303030",
        "input": "#121212",
        "accent": "#ff0033",
        "blue": "#3ea6ff",
    },
    "Dim": {
        "bg": "#151719",
        "panel": "#202326",
        "panel2": "#2c3034",
        "hover": "#3a3f44",
        "text": "#f2f3f5",
        "muted": "#aeb4ba",
        "border": "#353a40",
        "input": "#1b1e21",
        "accent": "#ff3355",
        "blue": "#5db6ff",
    },
    "Light": {
        "bg": "#f7f7f7",
        "panel": "#ffffff",
        "panel2": "#e9e9e9",
        "hover": "#dddddd",
        "text": "#111111",
        "muted": "#606060",
        "border": "#d3d3d3",
        "input": "#ffffff",
        "accent": "#ff0033",
        "blue": "#065fd4",
    },
}


def human_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "0:00"
    try:
        seconds = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "0:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def safe_thumb_name(title: str, episode: str) -> Path:
    key = hashlib.sha1(f"{title.casefold()}::{episode}".encode()).hexdigest()
    return APP_CACHE_DIR / "thumbnails" / f"{key}.jpg"


class VideoFrame(QFrame):
    doubleClicked = Signal()
    resized = Signal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class MainWindow(QMainWindow):
    library_scanned = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1360, 790)
        self.setMinimumSize(940, 580)

        self.state = AppState()
        self.backend = AniCliBackend()
        self.metadata = MetadataService()

        self.query = ""
        self.selected_index = 0
        self.selected_title = ""
        self.current_metadata: dict[str, Any] = {}
        self.episodes: list[str] = []
        self.current_episode = ""
        self.pending_episode: str | None = None
        self.current_stream: dict[str, Any] | None = None
        self.user_seeking = False
        self.busy = False
        self.was_maximized = False
        self.auto_next_fired = False
        self.resume_target: float | None = None
        self.resume_applied = False
        self.current_thumb_captured = False
        self.last_state_save = 0.0
        self._callback_id = 0
        self._metadata_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._image_callbacks: dict[str, Callable[[str], None]] = {}
        self.episode_widgets: dict[str, EpisodeCard] = {}
        self.recommendations: list[dict[str, Any]] = []
        self._recommendations_requested = False
        self._recommendations_failed = False
        self.local_files: list[str] = []
        self._library_scan_running = False

        self._fullscreen_activity = time.monotonic()
        self._last_cursor_pos = QCursor.pos()
        self._chrome_hidden = False
        self._sidebar_last_size = 360
        self._sidebar_visible = True
        self._sidebar_before_fullscreen = True
        self._page_anim = None

        self._build_ui()
        self.library_scanned.connect(self._library_scan_finished)
        self._setup_sidebar_animation()
        self._setup_icons()
        self.mpv = MPVController(self.video)
        self._connect_signals()
        self.apply_settings_to_ui()
        self.apply_style()
        self.refresh_home()

        QTimer.singleShot(180, self.start_mpv)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_mpv)
        self.poll_timer.start(500)

        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self.spin_loading)
        self.spinner_chars = ["◐", "◓", "◑", "◒"]
        self.spinner_index = 0
        self.loading_reason = ""

        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self.fullscreen_chrome_tick)
        self.fullscreen_timer.start(150)

        self._setup_shortcuts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.topbar = QFrame(objectName="topbar")
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(18, 10, 18, 10)
        top.setSpacing(10)

        self.brand_btn = QPushButton("AniView", objectName="brandButton")
        self.brand_btn.setToolTip("Home")
        self.brand_btn.clicked.connect(self.go_home)
        top.addWidget(self.brand_btn)
        top.addStretch(1)

        self.search = QLineEdit(objectName="globalSearch")
        self.search.setPlaceholderText("Search anime")
        self.search.setClearButtonEnabled(False)
        self.search.setToolTip("Type an anime title and press Enter  ( / )")
        self.search.returnPressed.connect(self.do_search)
        self.search.setMaximumWidth(640)
        self.search.setMinimumWidth(340)
        self.search.setFixedHeight(42)
        top.addWidget(self.search, 5)
        top.addStretch(1)

        self.quality = QComboBox(objectName="qualityButton")
        self.quality.addItems(["best", "1080", "720", "480", "360"])
        self.quality.setToolTip("Playback quality")
        self.quality.currentTextChanged.connect(self.quick_settings_changed)
        top.addWidget(self.quality)

        self.dub_btn = QPushButton("SUB", objectName="languageButton")
        self.dub_btn.setCheckable(True)
        self.dub_btn.setToolTip("Toggle subtitles / dub")
        self.dub_btn.toggled.connect(self.dub_toggled)
        top.addWidget(self.dub_btn)

        self.settings_btn = QPushButton("", objectName="settingsButton")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        top.addWidget(self.settings_btn)
        outer.addWidget(self.topbar)

        self.body = QFrame(objectName="appBody")
        body_layout = QHBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.left_nav = self._build_left_nav()
        body_layout.addWidget(self.left_nav)

        self.pages = QStackedWidget()
        body_layout.addWidget(self.pages, 1)
        outer.addWidget(self.body, 1)

        self.home_page = self._build_home_page()
        self.search_page = self._build_search_page()
        self.library_page = self._build_library_page()
        self.watch_page = self._build_watch_page()
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.search_page)
        self.pages.addWidget(self.library_page)
        self.pages.addWidget(self.watch_page)
        self.set_page(self.home_page)

    def _build_left_nav(self) -> QWidget:
        nav = QFrame(objectName="leftNav")
        nav.setFixedWidth(224)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(4)

        self.nav_home = QPushButton("  Home", objectName="navButton")
        self.nav_home.setCursor(Qt.PointingHandCursor)
        self.nav_home.clicked.connect(self.go_home)
        layout.addWidget(self.nav_home)

        self.nav_library = QPushButton("  Library", objectName="navButton")
        self.nav_library.setCursor(Qt.PointingHandCursor)
        self.nav_library.clicked.connect(self.go_library)
        layout.addWidget(self.nav_library)

        divider = QFrame(objectName="navDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        recent_head = QHBoxLayout()
        recent_label = QLabel("Recent", objectName="navSectionLabel")
        recent_head.addWidget(recent_label)
        recent_head.addStretch(1)
        layout.addLayout(recent_head)

        self.recent_nav_scroll = QScrollArea(objectName="recentNavScroll")
        self.recent_nav_scroll.setWidgetResizable(True)
        self.recent_nav_scroll.setFrameShape(QFrame.NoFrame)
        self.recent_nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recent_content = QWidget()
        self.recent_nav_layout = QVBoxLayout(recent_content)
        self.recent_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_nav_layout.setSpacing(2)
        self.recent_nav_layout.addStretch(1)
        self.recent_nav_scroll.setWidget(recent_content)
        layout.addWidget(self.recent_nav_scroll, 1)
        return nav

    def _build_library_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("libraryScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(30, 26, 30, 36)
        root.setSpacing(14)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_box.addWidget(QLabel("Your library", objectName="pageHeading"))
        title_box.addWidget(QLabel("Play anime and other video files already stored on your computer.", objectName="pageSubheading"))
        head.addLayout(title_box, 1)
        self.add_folder_btn = QPushButton("Add folder", objectName="secondaryButton")
        self.add_folder_btn.clicked.connect(self.choose_library_folder)
        head.addWidget(self.add_folder_btn)
        self.manage_folders_btn = QPushButton("Folders", objectName="secondaryButton")
        self.manage_folders_btn.clicked.connect(self.show_library_folders_menu)
        head.addWidget(self.manage_folders_btn)
        self.rescan_btn = QPushButton("Rescan", objectName="secondaryButton")
        self.rescan_btn.clicked.connect(self.scan_library)
        head.addWidget(self.rescan_btn)
        root.addLayout(head)

        self.library_folders_label = QLabel("No folders added yet.", objectName="libraryFolders")
        self.library_folders_label.setWordWrap(True)
        root.addWidget(self.library_folders_label)

        self.library_list_layout = QVBoxLayout()
        self.library_list_layout.setSpacing(7)
        root.addLayout(self.library_list_layout)
        root.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_home_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.home_layout = QVBoxLayout(content)
        self.home_layout.setContentsMargins(30, 26, 30, 36)
        self.home_layout.setSpacing(22)
        scroll.setWidget(content)
        return scroll

    def _build_search_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("searchScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.search_results_layout = QVBoxLayout(content)
        self.search_results_layout.setContentsMargins(34, 26, 34, 36)
        self.search_results_layout.setSpacing(12)
        self.search_heading = QLabel("Search", objectName="pageHeading")
        self.search_results_layout.addWidget(self.search_heading)
        self.search_status = QLabel("Search for an anime above.", objectName="muted")
        self.search_results_layout.addWidget(self.search_status)
        self.search_results_layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_watch_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        self.player_panel = QWidget()
        self.player_layout = QVBoxLayout(self.player_panel)
        self.player_layout.setContentsMargins(18, 16, 10, 14)
        self.player_layout.setSpacing(10)

        self.video = VideoFrame(objectName="video")
        self.video.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.video.setAttribute(Qt.WA_NativeWindow, True)
        self.video.setMinimumSize(600, 337)
        self.video.doubleClicked.connect(self.toggle_fullscreen)
        self.video.resized.connect(self.position_loading_overlay)
        self.player_layout.addWidget(self.video, 1)

        self.placeholder = QLabel("Select an episode\nChoose one from the episode panel →", self.video, objectName="placeholder")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.placeholder.resize(440, 90)

        self.loading_overlay = QLabel("", self.video, objectName="loadingOverlay")
        self.loading_overlay.setAlignment(Qt.AlignCenter)
        self.loading_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.loading_overlay.resize(240, 66)
        self.loading_overlay.hide()

        self.chrome = QFrame(objectName="playerChrome")
        chrome_layout = QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(6, 0, 6, 0)
        chrome_layout.setSpacing(6)

        self.title_label = QLabel("Nothing playing", objectName="videoTitle")
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        chrome_layout.addWidget(self.title_label)
        self.watch_meta = QLabel("Choose an episode to begin", objectName="watchMeta")
        chrome_layout.addWidget(self.watch_meta)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(9)
        self.time_label = QLabel("0:00", objectName="timeLabel")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.setToolTip("Seek")
        self.seek.sliderPressed.connect(lambda: setattr(self, "user_seeking", True))
        self.seek.sliderReleased.connect(self.seek_released)
        self.duration_label = QLabel("0:00", objectName="timeLabel")
        seek_row.addWidget(self.time_label)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.duration_label)
        chrome_layout.addLayout(seek_row)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        self.prev_ep = QToolButton(); self.prev_ep.setText("⏮"); self.prev_ep.setToolTip("Previous episode (P)")
        self.prev_ep.clicked.connect(lambda: self.change_episode(-1)); controls.addWidget(self.prev_ep)
        self.back10 = QToolButton(); self.back10.setText("↶ 10"); self.back10.setToolTip("Back 10 seconds (J)")
        self.back10.clicked.connect(lambda: self.seek_relative(-10)); controls.addWidget(self.back10)
        self.play_btn = QToolButton(); self.play_btn.setText("▶"); self.play_btn.setObjectName("playButton")
        self.play_btn.setToolTip("Play/Pause (Space or K)"); self.play_btn.clicked.connect(self.toggle_pause); controls.addWidget(self.play_btn)
        self.fwd10 = QToolButton(); self.fwd10.setText("10 ↷"); self.fwd10.setToolTip("Forward 10 seconds (L)")
        self.fwd10.clicked.connect(lambda: self.seek_relative(10)); controls.addWidget(self.fwd10)
        self.next_ep = QToolButton(); self.next_ep.setText("⏭"); self.next_ep.setToolTip("Next episode (N)")
        self.next_ep.clicked.connect(lambda: self.change_episode(1)); controls.addWidget(self.next_ep)
        controls.addStretch(1)
        self.sidebar_toggle_btn = QToolButton(); self.sidebar_toggle_btn.setText("Episodes")
        self.sidebar_toggle_btn.setObjectName("sidebarToggle")
        self.sidebar_toggle_btn.setToolTip("Show/hide episodes (E)")
        self.sidebar_toggle_btn.clicked.connect(lambda _checked=False: self.toggle_episode_sidebar()); controls.addWidget(self.sidebar_toggle_btn)
        self.mute_btn = QToolButton(); self.mute_btn.setText("🔊"); self.mute_btn.setToolTip("Mute (M)")
        self.mute_btn.clicked.connect(self.toggle_mute); controls.addWidget(self.mute_btn)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 130)
        self.volume.setFixedWidth(118)
        self.volume.valueChanged.connect(self.volume_changed)
        controls.addWidget(self.volume)
        self.fs_btn = QToolButton(); self.fs_btn.setText("⛶"); self.fs_btn.setToolTip("Fullscreen (F)")
        self.fs_btn.clicked.connect(self.toggle_fullscreen); controls.addWidget(self.fs_btn)
        chrome_layout.addLayout(controls)
        self.player_layout.addWidget(self.chrome)

        self.chrome_effect = QGraphicsOpacityEffect(self.chrome)
        self.chrome.setGraphicsEffect(self.chrome_effect)
        self.chrome_effect.setOpacity(1.0)
        self.chrome_anim = QPropertyAnimation(self.chrome_effect, b"opacity", self)
        self.chrome_anim.setDuration(220)
        self.chrome_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.chrome_anim.finished.connect(self._chrome_animation_finished)

        self.splitter.addWidget(self.player_panel)

        self.sidebar = QFrame(objectName="sidebar")
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(430)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 14, 14, 12)
        side.setSpacing(10)

        side_head = QHBoxLayout()
        self.side_title = QLabel("Episodes", objectName="sideTitle")
        side_head.addWidget(self.side_title, 1)
        self.sidebar_close_btn = QToolButton(objectName="sidebarClose")
        self.sidebar_close_btn.setText("×")
        self.sidebar_close_btn.setToolTip("Hide episode panel")
        self.sidebar_close_btn.clicked.connect(lambda _checked=False: self.toggle_episode_sidebar())
        side_head.addWidget(self.sidebar_close_btn)
        side.addLayout(side_head)

        self.episode_filter = QLineEdit(objectName="episodeSearch")
        self.episode_filter.setPlaceholderText("Filter episodes…")
        self.episode_filter.setClearButtonEnabled(True)
        self.episode_filter.textChanged.connect(self.filter_episodes)
        side.addWidget(self.episode_filter)

        self.episode_list = QListWidget(objectName="episodeList")
        self.episode_list.setSpacing(5)
        self.episode_list.itemClicked.connect(self.episode_clicked)
        side.addWidget(self.episode_list, 1)
        self.status = QLabel("Choose an anime to see episodes", objectName="status")
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        self.splitter.addWidget(self.sidebar)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([980, 360])
        return page

    def _connect_signals(self) -> None:
        self.backend.signals.search_done.connect(self.show_search_results)
        self.backend.signals.episodes_done.connect(self.show_episodes)
        self.backend.signals.stream_done.connect(self.play_stream)
        self.backend.signals.error.connect(self.show_error)
        self.metadata.signals.metadata_ready.connect(self._metadata_ready)
        self.metadata.signals.image_ready.connect(self._image_ready)
        self.metadata.signals.recommendations_ready.connect(self._recommendations_ready)

    def _setup_shortcuts(self) -> None:
        action = QAction(self)
        action.setShortcut(QKeySequence("F11"))
        action.triggered.connect(self.toggle_fullscreen)
        self.addAction(action)

    def _setup_sidebar_animation(self) -> None:
        self.sidebar_anim = QVariantAnimation(self)
        self.sidebar_anim.setDuration(240)
        self.sidebar_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.sidebar_anim.valueChanged.connect(self._sidebar_anim_value)
        self.sidebar_anim.finished.connect(self._sidebar_anim_finished)
        self._sidebar_anim_target_open = True

    def _themed_icon(self, names: list[str], fallback: QStyle.StandardPixmap | None = None) -> QIcon:
        for name in names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return icon
        if fallback is not None:
            return self.style().standardIcon(fallback)
        return QIcon()

    def _apply_button_icon(self, button, names: list[str], fallback: QStyle.StandardPixmap | None = None, text: str = "", size: int = 18) -> None:
        icon = self._themed_icon(names, fallback)
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(size, size))
        button.setText(text)

    def _setup_icons(self) -> None:
        asset_dir = Path(__file__).resolve().parent / "assets"
        app_icon = QIcon(str(asset_dir / "aniview.png"))
        self.setWindowIcon(app_icon)
        self.brand_btn.setIcon(app_icon)
        self.brand_btn.setIconSize(QSize(22, 22))

        home_icon = QIcon(str(asset_dir / "home.svg"))
        library_icon = QIcon(str(asset_dir / "library.svg"))
        if not home_icon.isNull():
            self.nav_home.setIcon(home_icon); self.nav_home.setIconSize(QSize(18, 18))
        if not library_icon.isNull():
            self.nav_library.setIcon(library_icon); self.nav_library.setIconSize(QSize(18, 18))

        settings_icon = QIcon(str(asset_dir / "settings.svg"))
        if not settings_icon.isNull():
            self.settings_btn.setIcon(settings_icon)
            self.settings_btn.setIconSize(QSize(17, 17))
            self.settings_btn.setText("")
        else:
            self._apply_button_icon(self.settings_btn, ["preferences-system-symbolic", "preferences-desktop-symbolic"], None, "", 16)
            if self.settings_btn.icon().isNull():
                self.settings_btn.setText("⚙")

        self._apply_button_icon(self.prev_ep, ["media-skip-backward-symbolic"], QStyle.SP_MediaSkipBackward, "", 18)
        self._apply_button_icon(self.back10, ["media-seek-backward-symbolic"], QStyle.SP_MediaSeekBackward, " 10", 16)
        self._apply_button_icon(self.fwd10, ["media-seek-forward-symbolic"], QStyle.SP_MediaSeekForward, "10 ", 16)
        self._apply_button_icon(self.next_ep, ["media-skip-forward-symbolic"], QStyle.SP_MediaSkipForward, "", 18)
        episodes_icon = QIcon(str(asset_dir / "episodes.svg"))
        if not episodes_icon.isNull():
            self.sidebar_toggle_btn.setIcon(episodes_icon)
            self.sidebar_toggle_btn.setIconSize(QSize(17, 17))
            self.sidebar_toggle_btn.setText(" Episodes")
        else:
            self._apply_button_icon(self.sidebar_toggle_btn, ["sidebar-show-right-symbolic", "view-right-pane-symbolic"], None, " Episodes", 16)
            if self.sidebar_toggle_btn.icon().isNull():
                self.sidebar_toggle_btn.setText("Episodes")
        self._apply_button_icon(self.sidebar_close_btn, ["window-close-symbolic", "dialog-close-symbolic"], QStyle.SP_TitleBarCloseButton, "", 14)
        self._apply_button_icon(self.fs_btn, ["view-fullscreen-symbolic"], QStyle.SP_TitleBarMaxButton, "", 17)
        self._set_play_visual(True)
        self._set_mute_visual(False)

    def _set_play_visual(self, paused: bool) -> None:
        if paused:
            self._apply_button_icon(self.play_btn, ["media-playback-start-symbolic"], QStyle.SP_MediaPlay, "", 18)
        else:
            self._apply_button_icon(self.play_btn, ["media-playback-pause-symbolic"], QStyle.SP_MediaPause, "", 18)

    def _set_mute_visual(self, muted: bool, volume: int | None = None) -> None:
        if muted or (volume is not None and int(volume) == 0):
            self._apply_button_icon(self.mute_btn, ["audio-volume-muted-symbolic"], None, "", 16)
            if self.mute_btn.icon().isNull():
                self.mute_btn.setText("🔇")
            return
        if volume is not None and int(volume) <= 35:
            self._apply_button_icon(self.mute_btn, ["audio-volume-low-symbolic"], None, "", 16)
        else:
            self._apply_button_icon(self.mute_btn, ["audio-volume-high-symbolic"], None, "", 16)
        if self.mute_btn.icon().isNull():
            self.mute_btn.setText("🔊")

    def set_page(self, page: QWidget) -> None:
        self.pages.setCurrentWidget(page)
        if hasattr(self, "nav_home"):
            self.nav_home.setProperty("active", page is self.home_page if hasattr(self, "home_page") else False)
            self.nav_library.setProperty("active", page is self.library_page if hasattr(self, "library_page") else False)
            for button in (self.nav_home, self.nav_library):
                button.style().unpolish(button); button.style().polish(button)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(170)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda w=page, e=effect: w.setGraphicsEffect(None))
        self._page_anim = anim
        anim.start()

    # ---------------------------------------------------------- metadata/images
    def next_token(self, prefix: str) -> str:
        self._callback_id += 1
        return f"{prefix}:{self._callback_id}"

    def request_metadata(self, title: str, callback: Callable[[dict[str, Any]], None]) -> None:
        token = self.next_token("meta")
        self._metadata_callbacks[token] = callback
        self.metadata.fetch_async(title, token)

    def _metadata_ready(self, token: str, data: object) -> None:
        callback = self._metadata_callbacks.pop(token, None)
        if callback:
            callback(dict(data or {}))

    def request_image(self, url: str | None, callback: Callable[[str], None]) -> None:
        if not url:
            callback("")
            return
        token = self.next_token("img")
        self._image_callbacks[token] = callback
        self.metadata.image_async(url, token)

    def _image_ready(self, token: str, path: str) -> None:
        callback = self._image_callbacks.pop(token, None)
        if callback:
            callback(path)

    def request_recommendations(self, retry: bool = False) -> None:
        if retry:
            self._recommendations_requested = False
            self._recommendations_failed = False
        if self._recommendations_requested:
            return
        self._recommendations_requested = True
        self.metadata.recommendations_async()

    def _recommendations_ready(self, rows: object) -> None:
        self.recommendations = [dict(x) for x in list(rows or [])]
        self._recommendations_failed = not bool(self.recommendations)
        if self.pages.currentWidget() is self.home_page:
            self.refresh_home()

    @staticmethod
    def set_label_image(label: CoverLabel, path: str) -> None:
        try:
            label.set_image(path)
        except RuntimeError:
            pass

    # ---------------------------------------------------------------- home
    def stop_playback_for_navigation(self) -> None:
        if not self.current_stream:
            return
        try:
            pos = self.mpv.request(["get_property", "time-pos"])
            duration = self.mpv.request(["get_property", "duration"])
            if pos is not None and duration:
                p, d = float(pos), float(duration)
                self.persist_progress(p, d, d > 30 and p >= d - 8, force_save=True)
        except Exception:
            pass
        self.mpv.command(["stop"])
        self.current_stream = None
        self.hide_loading()
        self._set_play_visual(True)

    def go_home(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        self.stop_playback_for_navigation()
        self.refresh_home()
        self.refresh_recent_nav()
        self.set_page(self.home_page)

    def go_library(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        self.stop_playback_for_navigation()
        self.refresh_library()
        self.set_page(self.library_page)

    def refresh_recent_nav(self) -> None:
        clear_layout(self.recent_nav_layout)
        rows = self.state.recent_anime(10)
        if not rows:
            empty = QLabel("Your recently watched anime will appear here.", objectName="navEmpty")
            empty.setWordWrap(True)
            self.recent_nav_layout.addWidget(empty)
            self.recent_nav_layout.addStretch(1)
            return
        for entry in rows:
            title = str(entry.get("title") or "Unknown")
            short = title if len(title) <= 27 else title[:24].rstrip() + "…"
            btn = QPushButton(short, objectName="recentNavButton")
            btn.setToolTip(title)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, e=dict(entry): self.open_history_entry(e))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, e=dict(entry): self.show_home_context(e, b.mapToGlobal(pos))
            )
            meta = entry.get("metadata") or {}
            artwork = meta.get("cover_url") or meta.get("banner_url")
            if artwork:
                self.request_image(artwork, lambda path, b=btn: self._set_nav_thumb(b, path))
            self.recent_nav_layout.addWidget(btn)
        self.recent_nav_layout.addStretch(1)

    @staticmethod
    def _set_nav_thumb(button: QPushButton, path: str) -> None:
        try:
            if path:
                button.setIcon(QIcon(path))
                button.setIconSize(QSize(26, 26))
        except RuntimeError:
            pass

    def focus_search(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def refresh_home(self) -> None:
        clear_layout(self.home_layout)
        self.refresh_recent_nav()

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(QLabel("Home", objectName="pageHeading"))
        titles.addWidget(QLabel("Pick up where you left off or discover something new.", objectName="pageSubheading"))
        head.addLayout(titles, 1)
        self.home_layout.addLayout(head)

        cont = self.state.continue_watching(10)
        if cont:
            self._add_home_section("Continue watching", cont, True)

        if self.recommendations:
            self._add_recommendations_section("Recommended", self.recommendations)
        elif self._recommendations_failed:
            placeholder = QFrame(objectName="recommendationLoading")
            row = QHBoxLayout(placeholder)
            row.setContentsMargins(18, 14, 18, 14)
            row.addWidget(QLabel("Recommendations are unavailable right now.", objectName="muted"), 1)
            retry = QPushButton("Retry", objectName="secondaryButton")
            retry.clicked.connect(lambda: (self.request_recommendations(True), self.refresh_home()))
            row.addWidget(retry)
            self.home_layout.addWidget(placeholder)
        else:
            self.request_recommendations()
            placeholder = QFrame(objectName="recommendationLoading")
            row = QHBoxLayout(placeholder)
            row.setContentsMargins(18, 18, 18, 18)
            row.addWidget(QLabel("Loading recommendations…", objectName="muted"))
            row.addStretch(1)
            self.home_layout.addWidget(placeholder)

        if not cont:
            hint = QFrame(objectName="homeHint")
            box = QHBoxLayout(hint)
            box.setContentsMargins(18, 14, 18, 14)
            label = QLabel("Your Continue Watching row will appear after you start an episode.", objectName="muted")
            box.addWidget(label, 1)
            browse = QPushButton("Search anime", objectName="secondaryButton")
            browse.clicked.connect(self.focus_search)
            box.addWidget(browse)
            self.home_layout.addWidget(hint)

        self.home_layout.addStretch(1)

    def _add_home_section(self, name: str, entries: list[dict[str, Any]], show_progress: bool) -> None:
        header = QHBoxLayout()
        label = QLabel(name, objectName="sectionHeading")
        header.addWidget(label)
        header.addStretch(1)
        count = QLabel(f"{len(entries)} item{'s' if len(entries) != 1 else ''}", objectName="sectionCount")
        header.addWidget(count)
        self.home_layout.addLayout(header)

        scroll = QScrollArea(objectName="shelfScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFixedHeight(245)
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 8)
        row.setSpacing(12)
        for entry in entries:
            card = HomeCard(entry, show_progress)
            card.activated.connect(self.open_history_entry)
            card.contextRequested.connect(lambda pos, e=dict(entry): self.show_home_context(e, pos))
            row.addWidget(card)
            meta = entry.get("metadata") or {}
            artwork = meta.get("banner_url") or meta.get("cover_url")
            if artwork:
                self.request_image(artwork, lambda path, c=card: self.set_label_image(c.poster, path))
            else:
                title = str(entry.get("title") or "")
                if title:
                    self.request_metadata(title, lambda data, c=card: self._apply_home_metadata(c, data))
        row.addStretch(1)
        scroll.setWidget(row_widget)
        self.home_layout.addWidget(scroll)

    def _add_recommendations_section(self, name: str, rows: list[dict[str, Any]]) -> None:
        header = QHBoxLayout()
        header.addWidget(QLabel(name, objectName="sectionHeading"))
        header.addStretch(1)
        note = QLabel("Popular right now", objectName="sectionCount")
        note.setToolTip("Recommendations currently use popular/trending titles, not a personal profile.")
        header.addWidget(note)
        self.home_layout.addLayout(header)

        scroll = QScrollArea(objectName="recommendationScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFixedHeight(345)
        holder = QWidget()
        row_layout = QHBoxLayout(holder)
        row_layout.setContentsMargins(0, 0, 0, 8)
        row_layout.setSpacing(12)
        for data in rows[:14]:
            card = RecommendationCard(data)
            card.activated.connect(self.open_recommendation)
            card.contextRequested.connect(lambda pos, d=dict(data): self.show_recommendation_context(d, pos))
            artwork = data.get("cover_url")
            if artwork:
                self.request_image(artwork, lambda path, c=card: self.set_label_image(c.poster, path))
            row_layout.addWidget(card)
        row_layout.addStretch(1)
        scroll.setWidget(holder)
        self.home_layout.addWidget(scroll)

    def open_recommendation(self, title: str) -> None:
        self.search.setText(title)
        self.do_search()

    def show_recommendation_context(self, data: dict[str, Any], global_pos: object) -> None:
        title = str(data.get("english_title") or data.get("title") or "Anime")
        menu = QMenu(self)
        search_action = menu.addAction("Search for this title")
        copy_action = menu.addAction("Copy title")
        chosen = menu.exec(global_pos)
        if chosen is search_action:
            self.open_recommendation(title)
        elif chosen is copy_action:
            QApplication.clipboard().setText(title)

    def show_home_context(self, entry: dict[str, Any], global_pos: object) -> None:
        title = str(entry.get("title") or "Anime")
        episode = str(entry.get("episode") or "1")
        menu = QMenu(self)
        resume_action = menu.addAction(f"Resume Episode {episode}")
        start_action = menu.addAction("Start from Episode 1")
        menu.addSeparator()
        watched_action = menu.addAction("Mark anime as watched")
        unwatched_action = menu.addAction("Mark anime as unwatched")
        remove_action = menu.addAction("Remove from history")
        menu.addSeparator()
        copy_action = menu.addAction("Copy title")
        chosen = menu.exec(global_pos)
        if chosen is resume_action:
            self.open_history_entry(entry)
        elif chosen is start_action:
            fresh = dict(entry); fresh["episode"] = "1"; fresh["position"] = 0
            self.open_history_entry(fresh)
        elif chosen is watched_action:
            self.state.mark_title_watched(title, True); self.refresh_home()
        elif chosen is unwatched_action:
            self.state.mark_title_watched(title, False); self.refresh_home()
        elif chosen is remove_action:
            self.state.remove_title(title); self.refresh_home()
        elif chosen is copy_action:
            QApplication.clipboard().setText(title)

    def _apply_home_metadata(self, card: HomeCard, data: dict[str, Any]) -> None:
        try:
            artwork = data.get("banner_url") or data.get("cover_url")
            if artwork:
                self.request_image(artwork, lambda path, c=card: self.set_label_image(c.poster, path))
        except RuntimeError:
            pass

    def open_history_entry(self, entry: object) -> None:
        self.sidebar_toggle_btn.setEnabled(True)
        item = dict(entry or {})
        self.query = str(item.get("query") or item.get("title") or "")
        self.current_episode = ""
        self.selected_index = int(item.get("index") or 1)
        self.selected_title = str(item.get("title") or self.query)
        self.current_metadata = dict(item.get("metadata") or {})
        self.pending_episode = str(item.get("episode") or "1")
        self.search.setText(self.selected_title)
        self.set_page(self.watch_page)
        self.show_loading("Loading episodes")
        self.set_busy(f"Loading {self.selected_title}…", use_cursor=False)
        self.backend.episodes_async(
            self.query,
            self.selected_index,
            self.selected_title,
            self.quality.currentText(),
            self.dub_btn.isChecked(),
        )

    # -------------------------------------------------------------- local files
    def choose_library_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add anime folder", str(Path.home()))
        if not folder:
            return
        self.state.add_library_folder(folder)
        self.refresh_library()

    def show_library_folders_menu(self) -> None:
        menu = QMenu(self)
        add = menu.addAction("Add folder…")
        folders = self.state.library_folders()
        remove_actions: dict[QAction, str] = {}
        if folders:
            menu.addSeparator()
            for folder in folders:
                action = menu.addAction(f"Remove  {Path(folder).name or folder}")
                action.setToolTip(folder)
                remove_actions[action] = folder
        chosen = menu.exec(self.manage_folders_btn.mapToGlobal(self.manage_folders_btn.rect().bottomLeft()))
        if chosen is add:
            self.choose_library_folder()
        elif chosen in remove_actions:
            self.state.remove_library_folder(remove_actions[chosen])
            self.refresh_library()

    def refresh_library(self) -> None:
        folders = self.state.library_folders()
        if folders:
            pretty = "   •   ".join(Path(x).name or x for x in folders)
            self.library_folders_label.setText(f"Watching: {pretty}")
        else:
            self.library_folders_label.setText("No folders added yet. Add a folder containing your own video files.")
        self.scan_library()

    def scan_library(self) -> None:
        if self._library_scan_running:
            return
        folders = self.state.library_folders()
        clear_layout(self.library_list_layout)
        if not folders:
            empty = QFrame(objectName="libraryEmpty")
            box = QVBoxLayout(empty)
            box.setContentsMargins(30, 34, 30, 34)
            title = QLabel("Bring your downloaded anime into AniView", objectName="emptyTitle")
            title.setAlignment(Qt.AlignCenter)
            detail = QLabel("Choose a folder and AniView will find common video files inside it. Nothing is uploaded.", objectName="muted")
            detail.setAlignment(Qt.AlignCenter); detail.setWordWrap(True)
            add = QPushButton("Add a folder", objectName="primaryButton")
            add.clicked.connect(self.choose_library_folder)
            row = QHBoxLayout(); row.addStretch(1); row.addWidget(add); row.addStretch(1)
            box.addWidget(title); box.addWidget(detail); box.addLayout(row)
            self.library_list_layout.addWidget(empty)
            return

        self._library_scan_running = True
        self.rescan_btn.setEnabled(False)
        self.library_list_layout.addWidget(QLabel("Scanning folders…", objectName="muted"))
        threading.Thread(target=self._scan_library_worker, args=(list(folders),), daemon=True).start()

    def _scan_library_worker(self, folders: list[str]) -> None:
        extensions = {".mkv", ".mp4", ".webm", ".m4v", ".avi", ".mov", ".ts", ".m2ts"}
        files: list[str] = []
        seen: set[str] = set()
        for folder in folders:
            root = Path(folder).expanduser()
            if not root.exists() or not root.is_dir():
                continue
            try:
                for candidate in root.rglob("*"):
                    if len(files) >= 1000:
                        break
                    try:
                        if candidate.is_file() and candidate.suffix.lower() in extensions:
                            value = str(candidate.resolve())
                            if value not in seen:
                                seen.add(value); files.append(value)
                    except OSError:
                        continue
            except OSError:
                continue
        files.sort(key=lambda x: Path(x).name.casefold())
        self.library_scanned.emit(files)

    def _library_scan_finished(self, rows: object) -> None:
        self._library_scan_running = False
        self.rescan_btn.setEnabled(True)
        self.local_files = [str(x) for x in list(rows or [])]
        clear_layout(self.library_list_layout)
        if not self.local_files:
            empty = QLabel("No supported video files were found in the selected folders.", objectName="muted")
            empty.setWordWrap(True)
            self.library_list_layout.addWidget(empty)
            return
        count = QLabel(f"{len(self.local_files)} local video{'s' if len(self.local_files) != 1 else ''}", objectName="sectionCount")
        self.library_list_layout.addWidget(count)
        for path in self.local_files[:500]:
            card = LocalFileCard(path)
            card.activated.connect(self.play_local_file)
            card.contextRequested.connect(lambda pos, f=path: self.show_local_file_context(f, pos))
            self.library_list_layout.addWidget(card)
        if len(self.local_files) > 500:
            self.library_list_layout.addWidget(QLabel("Showing the first 500 files. Narrow the folders if you need a smaller library.", objectName="muted"))

    def play_local_file(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, APP_NAME, "That video file no longer exists.")
            return
        self.stop_playback_for_navigation()
        self.query = ""
        self.selected_index = 0
        self.selected_title = p.stem
        self.current_episode = ""
        self.current_metadata = {}
        self.episodes = []
        self.current_stream = {"url": str(p), "media_title": p.stem, "local": True}
        self.sidebar_toggle_btn.setEnabled(False)
        self.set_page(self.watch_page)
        self.title_label.setText(p.stem)
        self.watch_meta.setText(f"Local file   •   {p.parent}")
        self.placeholder.hide()
        self.status.setText("Playing local file")
        if self._sidebar_visible:
            self.toggle_episode_sidebar(force=False)
        self.show_loading("Loading local video")
        self.mpv.load(self.current_stream, self.volume.value())

    def show_local_file_context(self, path: str, global_pos: object) -> None:
        p = Path(path)
        menu = QMenu(self)
        play = menu.addAction("Play")
        reveal = menu.addAction("Show in folder")
        copy = menu.addAction("Copy file path")
        chosen = menu.exec(global_pos)
        if chosen is play:
            self.play_local_file(path)
        elif chosen is reveal:
            try:
                subprocess.Popen(["xdg-open", str(p.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
        elif chosen is copy:
            QApplication.clipboard().setText(str(p))

    # ---------------------------------------------------------------- search
    def do_search(self) -> None:
        query = self.search.text().strip()
        if not query:
            return
        self.stop_playback_for_navigation()
        self.query = query
        self.selected_index = 0
        self.selected_title = ""
        self.current_episode = ""
        self.episodes = []
        self.current_metadata = {}
        self.set_page(self.search_page)
        clear_layout(self.search_results_layout)
        self.search_heading = QLabel(f"Results for “{query}”", objectName="pageHeading")
        self.search_results_layout.addWidget(self.search_heading)
        self.search_status = QLabel("Searching…", objectName="muted")
        self.search_results_layout.addWidget(self.search_status)
        self.search_results_layout.addStretch(1)
        self.set_busy(f"Searching for {query}…")
        self.backend.search_async(query)

    def show_search_results(self, results: object, query: str) -> None:
        if str(query) != self.query:
            return
        self.clear_busy()
        clear_layout(self.search_results_layout)
        rows = list(results or [])

        head = QHBoxLayout()
        self.search_heading = QLabel(f"Results for “{self.query}”", objectName="pageHeading")
        head.addWidget(self.search_heading)
        head.addStretch(1)
        if rows:
            head.addWidget(QLabel(f"{min(len(rows), 30)} results", objectName="sectionCount"))
        self.search_results_layout.addLayout(head)

        if not rows:
            empty = QFrame(objectName="searchEmpty")
            box = QVBoxLayout(empty)
            box.setContentsMargins(28, 36, 28, 36)
            title = QLabel("No anime found", objectName="emptyTitle")
            title.setAlignment(Qt.AlignCenter)
            hint = QLabel("Try a shorter title, the English title, or a different spelling.", objectName="muted")
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)
            retry = QPushButton("Edit search", objectName="ctaButton")
            retry.clicked.connect(self.focus_search)
            row = QHBoxLayout(); row.addStretch(1); row.addWidget(retry); row.addStretch(1)
            box.addWidget(title); box.addWidget(hint); box.addLayout(row)
            self.search_results_layout.addWidget(empty)
            self.search_results_layout.addStretch(1)
            return

        helper = QLabel("Choose a title to see its episodes.", objectName="pageSubheading")
        self.search_results_layout.addWidget(helper)
        for index, title in rows[:30]:
            card = SearchResultCard(int(index), str(title))
            card.activated.connect(self.choose_anime)
            self.search_results_layout.addWidget(card)
            self.request_metadata(str(title), lambda data, c=card: self._apply_search_metadata(c, data))
        self.search_results_layout.addStretch(1)

    def _apply_search_metadata(self, card: SearchResultCard, data: dict[str, Any]) -> None:
        try:
            card.apply_metadata(data)
            if data.get("cover_url"):
                self.request_image(data["cover_url"], lambda path, c=card: self.set_label_image(c.poster, path))
        except RuntimeError:
            pass

    def choose_anime(self, index: int, title: str) -> None:
        self.sidebar_toggle_btn.setEnabled(True)
        self.current_episode = ""
        self.current_stream = None
        self.selected_index = int(index)
        self.selected_title = title
        self.current_metadata = self.metadata.cached(title) or {}
        self.pending_episode = None
        self.set_page(self.watch_page)
        self.show_loading("Loading episodes")
        self.set_busy(f"Loading episodes for {title}…", use_cursor=False)
        self.backend.episodes_async(
            self.query,
            self.selected_index,
            title,
            self.quality.currentText(),
            self.dub_btn.isChecked(),
        )
        self.request_metadata(title, lambda data, t=title: self.set_current_metadata(t, data))

    def set_current_metadata(self, title: str, data: dict[str, Any]) -> None:
        if title != self.selected_title or not data:
            return
        self.current_metadata = data
        self.refresh_episode_images()
        self.update_watch_meta()

    # --------------------------------------------------------------- episodes
    def show_episodes(self, episodes: object, title: str, index: int) -> None:
        if self.pages.currentWidget() is not self.watch_page:
            return
        if title != self.selected_title or int(index) != int(self.selected_index):
            return
        self.clear_busy()
        self.hide_loading()
        self.selected_title = title
        self.selected_index = int(index)
        self.episodes = [str(x) for x in list(episodes or [])]
        self.side_title.setText(f"Episodes   {len(self.episodes)}")
        self.episode_filter.blockSignals(True)
        self.episode_filter.clear()
        self.episode_filter.blockSignals(False)
        self.episode_list.clear()
        self.episode_widgets.clear()

        self.placeholder.setText(f"{title}\nSelect an episode from the panel →")
        self.placeholder.show()
        self.title_label.setText(title)
        self.update_watch_meta()

        for ep in self.episodes:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, ep)
            item.setSizeHint(QSize(340, 82))
            widget = EpisodeCard(ep)
            saved = self.state.progress_for(self.selected_title, ep) or {}
            widget.set_progress(
                float(saved.get("position") or 0),
                float(saved.get("duration") or 0),
                bool(saved.get("finished")),
            )
            self.episode_list.addItem(item)
            self.episode_list.setItemWidget(item, widget)
            self.episode_widgets[ep] = widget
            thumb = safe_thumb_name(self.selected_title, ep)
            if thumb.exists():
                widget.thumb.set_image(thumb)
        self.refresh_episode_images()
        self.status.setText("Select an episode to play")
        if not self._sidebar_visible:
            self.toggle_episode_sidebar(force=True)
        if self.pending_episode and self.pending_episode in self.episodes:
            ep = self.pending_episode
            self.pending_episode = None
            QTimer.singleShot(150, lambda e=ep: self.resolve_episode(e))
        elif self.episodes:
            self.episode_list.setCurrentRow(0)

    def refresh_episode_images(self) -> None:
        if not self.episode_widgets:
            return
        fallback = self.current_metadata.get("banner_url") or self.current_metadata.get("cover_url")
        if not fallback:
            return
        for ep, widget in list(self.episode_widgets.items()):
            thumb = safe_thumb_name(self.selected_title, ep)
            if thumb.exists():
                widget.thumb.set_image(thumb)
            else:
                self.request_image(fallback, lambda path, w=widget: self.set_label_image(w.thumb, path))

    def episode_clicked(self, item: QListWidgetItem) -> None:
        ep = str(item.data(Qt.UserRole) or "")
        if ep:
            self.resolve_episode(ep)

    def filter_episodes(self, text: str) -> None:
        needle = text.strip().casefold()
        visible = 0
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            ep = str(item.data(Qt.UserRole) or "")
            label = f"episode {ep}".casefold()
            match = not needle or needle in ep.casefold() or needle in label
            item.setHidden(not match)
            if match:
                visible += 1
        if needle:
            self.status.setText(f"{visible} episode{'s' if visible != 1 else ''} match")
        elif self.episodes:
            self.status.setText("Select an episode to play" if not self.current_episode else f"Playing Episode {self.current_episode}")

    def toggle_episode_sidebar(self, force: bool | None = None) -> None:
        if self.isFullScreen():
            return

        show = (not self._sidebar_visible) if force is None else bool(force)
        if force is not None and show == self._sidebar_visible:
            return

        self.sidebar_anim.stop()
        current = max(0, int(self.sidebar.width()))

        if show:
            target = max(310, min(430, int(self._sidebar_last_size or 360)))
            self._sidebar_visible = True
            self._sidebar_anim_target_open = True
            self.sidebar.show()
            # Release the collapsed constraints before animating open.
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(430)
            self.sidebar_toggle_btn.setToolTip("Hide episodes (E)")
            self.sidebar_toggle_btn.setProperty("open", True)
        else:
            target = 0
            if current > 20:
                self._sidebar_last_size = max(310, min(430, current))
            self._sidebar_visible = False
            self._sidebar_anim_target_open = False
            self.sidebar_toggle_btn.setToolTip("Show episodes (E)")
            self.sidebar_toggle_btn.setProperty("open", False)

        self.sidebar_toggle_btn.style().unpolish(self.sidebar_toggle_btn)
        self.sidebar_toggle_btn.style().polish(self.sidebar_toggle_btn)
        self.sidebar_anim.setStartValue(current)
        self.sidebar_anim.setEndValue(target)
        self.sidebar_anim.start()

    def _sidebar_anim_value(self, value: object) -> None:
        try:
            width = max(0, int(value))
        except (TypeError, ValueError):
            return
        # Fix the pane to the animated width and explicitly give that width to
        # QSplitter. This works reliably even after a pane was fully collapsed.
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        total = max(1, self.splitter.width())
        self.splitter.setSizes([max(1, total - width), width])

    def _sidebar_anim_finished(self) -> None:
        if self._sidebar_anim_target_open:
            target = max(310, min(430, int(self._sidebar_last_size or 360)))
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(430)
            self.splitter.setSizes([max(1, self.splitter.width() - target), target])
            self.sidebar.show()
        else:
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(0)
            self.splitter.setSizes([max(1, self.splitter.width()), 0])

    def update_watch_meta(self) -> None:
        pieces: list[str] = []
        if self.current_episode:
            try:
                idx = self.episodes.index(str(self.current_episode)) + 1
                pieces.append(f"Episode {self.current_episode}  •  {idx} of {len(self.episodes)}")
            except ValueError:
                pieces.append(f"Episode {self.current_episode}")
        elif self.episodes:
            pieces.append(f"{len(self.episodes)} episodes")
        meta = self.current_metadata or {}
        if meta.get("year"):
            pieces.append(str(meta["year"]))
        if meta.get("format"):
            pieces.append(str(meta["format"]).replace("_", " ").title())
        genres = meta.get("genres") or []
        if genres:
            pieces.append(" · ".join(str(x) for x in genres[:3]))
        self.watch_meta.setText("   •   ".join(pieces) if pieces else "Choose an episode to begin")

    def resolve_episode(self, episode: str) -> None:
        if not self.query or not self.selected_index:
            return
        self.current_episode = str(episode)
        self.auto_next_fired = False
        self.current_thumb_captured = False
        self.resume_applied = False
        self.current_stream = None
        saved = self.state.progress_for(self.selected_title, self.current_episode) or {}
        duration = float(saved.get("duration") or 0)
        position = float(saved.get("position") or 0)
        if self.state.settings.get("resume_playback", True) and position > 10 and (duration <= 0 or position < duration - 45):
            self.resume_target = position
        else:
            self.resume_target = None
        self.title_label.setText(f"{self.selected_title} — Episode {episode}")
        self.update_watch_meta()
        self.status.setText(f"Resolving Episode {episode}…")
        self.show_loading(f"Resolving Episode {episode}")
        self.backend.resolve_async(
            self.query,
            self.selected_index,
            self.current_episode,
            self.selected_title,
            self.quality.currentText(),
            self.dub_btn.isChecked(),
        )
        self.mark_episode_playing(self.current_episode)

    def play_stream(self, stream: object, title: str, episode: str) -> None:
        if self.pages.currentWidget() is not self.watch_page:
            return
        if title != self.selected_title or str(episode) != str(self.current_episode):
            return
        self.current_stream = dict(stream or {})
        self.placeholder.hide()
        self.title_label.setText(self.current_stream.get("media_title") or f"{title} — Episode {episode}")
        self.status.setText(f"Playing Episode {episode}")
        self.current_episode = str(episode)
        self.update_watch_meta()
        self.show_loading("Loading video")
        self.mpv.load(self.current_stream, self.volume.value())
        self.mark_episode_playing(self.current_episode)

    def mark_episode_playing(self, episode: str) -> None:
        for ep, widget in self.episode_widgets.items():
            widget.set_playing(ep == str(episode))
        for row in range(self.episode_list.count()):
            item = self.episode_list.item(row)
            if str(item.data(Qt.UserRole)) == str(episode):
                self.episode_list.setCurrentRow(row)
                self.episode_list.scrollToItem(item)
                break
        self.update_watch_meta()

    def change_episode(self, delta: int) -> None:
        if not self.episodes:
            return
        try:
            idx = self.episodes.index(str(self.current_episode))
        except ValueError:
            idx = 0
        new_idx = idx + delta
        if 0 <= new_idx < len(self.episodes):
            self.resolve_episode(self.episodes[new_idx])
        elif delta > 0:
            self.status.setText("You reached the last episode in this listing.")

    # ---------------------------------------------------------------- player
    def start_mpv(self) -> None:
        try:
            self.mpv.start()
        except Exception as exc:
            self.show_error(str(exc))

    def toggle_pause(self) -> None:
        paused = self.mpv.request(["get_property", "pause"])
        if paused is not None:
            self.mpv.command(["set_property", "pause", not bool(paused)])

    def seek_relative(self, seconds: int) -> None:
        self.mpv.command(["seek", seconds, "relative"])
        self.note_fullscreen_activity()

    def seek_released(self) -> None:
        duration = self.mpv.request(["get_property", "duration"])
        if duration:
            target = self.seek.value() / 1000.0 * float(duration)
            self.mpv.command(["set_property", "time-pos", target])
        self.user_seeking = False

    def volume_changed(self, value: int) -> None:
        self.mpv.command(["set_property", "volume", int(value)])
        self.state.settings["volume"] = int(value)
        self._set_mute_visual(False, value)

    def toggle_mute(self) -> None:
        muted = self.mpv.request(["get_property", "mute"])
        if muted is None:
            return
        new = not bool(muted)
        self.mpv.command(["set_property", "mute", new])
        self._set_mute_visual(new, self.volume.value())

    def seek_percent(self, pct: int) -> None:
        duration = self.mpv.request(["get_property", "duration"])
        if duration:
            self.mpv.command(["set_property", "time-pos", float(duration) * pct / 100.0])

    def poll_mpv(self) -> None:
        pos = self.mpv.request(["get_property", "time-pos"])
        duration = self.mpv.request(["get_property", "duration"])
        paused = self.mpv.request(["get_property", "pause"])
        eof = self.mpv.request(["get_property", "eof-reached"])
        paused_cache = self.mpv.request(["get_property", "paused-for-cache"])
        cache_state = self.mpv.request(["get_property", "cache-buffering-state"])
        video_format = self.mpv.request(["get_property", "video-format"])
        current_path = self.mpv.request(["get_property", "path"])
        stream_matches = bool(self.current_stream and current_path == self.current_stream.get("url"))

        if duration:
            d = float(duration)
            self.duration_label.setText(human_time(d))
            if pos is not None:
                p = float(pos)
                self.time_label.setText(human_time(p))
                if not self.user_seeking:
                    self.seek.setValue(int(max(0, min(1000, p / d * 1000))))

                if stream_matches and self.resume_target and not self.resume_applied and d > 0:
                    target = min(float(self.resume_target), max(0.0, d - 45))
                    if target > 10:
                        self.mpv.command(["set_property", "time-pos", target])
                    self.resume_applied = True

                if stream_matches:
                    self.persist_progress(p, d, bool(eof) or (d > 30 and p >= d - 8))
                    self.capture_episode_thumbnail(p)

        if paused is not None:
            self._set_play_visual(bool(paused))

        if stream_matches and paused_cache:
            try:
                pct = int(float(cache_state or 0))
            except (TypeError, ValueError):
                pct = 0
            self.show_loading(f"Buffering{f'  {pct}%' if pct else ''}")
        elif stream_matches and video_format:
            self.hide_loading()

        if stream_matches and eof and not self.auto_next_fired:
            self.auto_next_fired = True
            self.persist_progress(float(pos or duration or 0), float(duration or 0), True, force_save=True)
            if self.state.settings.get("autoplay_next", True):
                QTimer.singleShot(700, lambda: self.change_episode(1))

    def persist_progress(self, position: float, duration: float, finished: bool, force_save: bool = False) -> None:
        if not (self.query and self.selected_index and self.selected_title and self.current_episode):
            return
        self.state.update_progress(
            query=self.query,
            index=self.selected_index,
            title=self.selected_title,
            episode=self.current_episode,
            position=position,
            duration=duration,
            metadata=self.current_metadata,
            finished=finished,
        )
        widget = self.episode_widgets.get(self.current_episode)
        if widget:
            widget.set_progress(position, duration, finished)
        now = time.monotonic()
        if force_save or now - self.last_state_save >= 5:
            self.state.save()
            self.last_state_save = now

    def capture_episode_thumbnail(self, position: float) -> None:
        if self.current_thumb_captured or position < 20 or not self.current_episode or not self.selected_title:
            return
        path = safe_thumb_name(self.selected_title, self.current_episode)
        if path.exists():
            self.current_thumb_captured = True
            return
        self.current_thumb_captured = True
        self.mpv.screenshot(path)
        QTimer.singleShot(1200, lambda p=path, ep=self.current_episode: self.refresh_captured_thumbnail(p, ep))

    def refresh_captured_thumbnail(self, path: Path, episode: str) -> None:
        if not path.exists():
            return
        widget = self.episode_widgets.get(str(episode))
        if widget:
            widget.thumb.set_image(path)

    # --------------------------------------------------------------- loading
    def position_loading_overlay(self) -> None:
        self.placeholder.move(max(0, (self.video.width() - self.placeholder.width()) // 2), max(0, (self.video.height() - self.placeholder.height()) // 2))
        self.loading_overlay.move(max(0, (self.video.width() - self.loading_overlay.width()) // 2), max(0, (self.video.height() - self.loading_overlay.height()) // 2))

    def show_loading(self, reason: str) -> None:
        self.loading_reason = reason
        if hasattr(self, "status"):
            self.status.setText(reason)
        self.spinner_index = 0
        self.loading_overlay.setText(f"{self.spinner_chars[0]}  {reason}")
        self.loading_overlay.show()
        self.loading_overlay.raise_()
        if not self.spinner_timer.isActive():
            self.spinner_timer.start(140)

    def spin_loading(self) -> None:
        if not self.loading_overlay.isVisible():
            self.spinner_timer.stop()
            return
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        self.loading_overlay.setText(f"{self.spinner_chars[self.spinner_index]}  {self.loading_reason}")
        self.loading_overlay.raise_()

    def hide_loading(self) -> None:
        self.loading_overlay.hide()
        self.spinner_timer.stop()

    # ------------------------------------------------------------- fullscreen
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return
        self.was_maximized = self.isMaximized()
        self._sidebar_before_fullscreen = self._sidebar_visible
        self.topbar.hide()
        self.left_nav.hide()
        self.sidebar.hide()
        self.title_label.hide()
        self.watch_meta.hide()
        self.player_layout.setContentsMargins(0, 0, 0, 0)
        self.showFullScreen()
        self._apply_button_icon(self.fs_btn, ["view-restore-symbolic"], QStyle.SP_TitleBarNormalButton, "", 17)
        self.note_fullscreen_activity()
        self.show_chrome()

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        self.showNormal()
        if self.was_maximized:
            self.showMaximized()
        self.topbar.show()
        self.left_nav.show()
        self.sidebar.show()
        if self._sidebar_before_fullscreen:
            self._sidebar_visible = True
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(430)
            self.splitter.setSizes([max(600, self.width() - self._sidebar_last_size), self._sidebar_last_size])
            self.sidebar_toggle_btn.setToolTip("Hide episodes (E)")
        else:
            self._sidebar_visible = False
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(0)
            self.splitter.setSizes([max(1, self.width()), 0])
            self.sidebar_toggle_btn.setToolTip("Show episodes (E)")
        self.title_label.show()
        self.watch_meta.show()
        self.player_layout.setContentsMargins(18, 16, 10, 14)
        self._apply_button_icon(self.fs_btn, ["view-fullscreen-symbolic"], QStyle.SP_TitleBarMaxButton, "", 17)
        self.show_chrome(immediate=True)

    def note_fullscreen_activity(self) -> None:
        self._fullscreen_activity = time.monotonic()
        if self.isFullScreen():
            self.show_chrome()

    def fullscreen_chrome_tick(self) -> None:
        if not self.isFullScreen():
            return
        pos = QCursor.pos()
        if (pos - self._last_cursor_pos).manhattanLength() > 2:
            self._last_cursor_pos = pos
            self._fullscreen_activity = time.monotonic()
            self.show_chrome()
        local = self.mapFromGlobal(pos)
        if local.y() >= self.height() - 140:
            self._fullscreen_activity = time.monotonic()
            self.show_chrome()
        elif time.monotonic() - self._fullscreen_activity > 2.4:
            self.hide_chrome()

    def show_chrome(self, immediate: bool = False) -> None:
        if not self.chrome.isVisible():
            self.chrome.show()
        self._chrome_hidden = False
        self.chrome_anim.stop()
        if immediate:
            self.chrome_effect.setOpacity(1.0)
            return
        self.chrome_anim.setStartValue(self.chrome_effect.opacity())
        self.chrome_anim.setEndValue(1.0)
        self.chrome_anim.start()

    def hide_chrome(self) -> None:
        if self._chrome_hidden or not self.isFullScreen():
            return
        self._chrome_hidden = True
        self.chrome_anim.stop()
        self.chrome_anim.setStartValue(self.chrome_effect.opacity())
        self.chrome_anim.setEndValue(0.0)
        self.chrome_anim.start()

    def _chrome_animation_finished(self) -> None:
        if self._chrome_hidden and self.isFullScreen() and self.chrome_effect.opacity() < 0.05:
            self.chrome.hide()

    # --------------------------------------------------------------- settings
    def quick_settings_changed(self) -> None:
        if not hasattr(self, "state"):
            return
        self.state.settings["quality"] = self.quality.currentText()
        self.state.save()

    def dub_toggled(self, on: bool) -> None:
        self.dub_btn.setText("DUB" if on else "SUB")
        if hasattr(self, "state"):
            self.state.settings["dub"] = bool(on)
            self.state.save()

    def apply_settings_to_ui(self) -> None:
        settings = self.state.settings
        self.quality.blockSignals(True)
        self.quality.setCurrentText(str(settings.get("quality", "best")))
        self.quality.blockSignals(False)
        self.dub_btn.blockSignals(True)
        self.dub_btn.setChecked(bool(settings.get("dub", False)))
        self.dub_btn.setText("DUB" if self.dub_btn.isChecked() else "SUB")
        self.dub_btn.blockSignals(False)
        self.volume.blockSignals(True)
        self.volume.setValue(int(settings.get("volume", 100)))
        self.volume.blockSignals(False)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.state.settings, self)
        if dialog.exec():
            self.state.settings.update(dialog.values())
            self.state.save()
            self.apply_settings_to_ui()
            self.mpv.command(["set_property", "volume", self.volume.value()])
            self.apply_style()

    # ---------------------------------------------------------------- style
    def apply_style(self) -> None:
        theme_name = str(self.state.settings.get("theme", "Dark"))
        c = THEMES.get(theme_name, THEMES["Dark"])
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {c['bg']};
                color: {c['text']};
                font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
                font-size: 14px;
            }}
            QLabel {{ background: transparent; }}

            /* ---------- app bar ---------- */
            #topbar {{
                background: {c['bg']};
                border-bottom: 1px solid {c['border']};
            }}
            #appBody {{ background: {c['bg']}; }}
            #leftNav {{
                background: {c['bg']};
                border-right: 1px solid {c['border']};
            }}
            #navButton, #recentNavButton {{
                background: transparent;
                border: 0;
                border-radius: 10px;
                text-align: left;
                padding: 9px 12px;
                min-height: 24px;
            }}
            #navButton:hover, #recentNavButton:hover {{ background: {c['panel2']}; }}
            #navButton[active="true"] {{ background: {c['panel2']}; font-weight: 750; }}
            #recentNavButton {{
                color: {c['text']};
                font-size: 13px;
                padding: 8px 10px;
            }}
            #navSectionLabel {{
                color: {c['muted']};
                font-size: 12px;
                font-weight: 750;
                padding: 9px 10px 5px 10px;
            }}
            #navEmpty {{ color: {c['muted']}; font-size: 12px; padding: 8px 10px; }}
            #navDivider {{ background: {c['border']}; margin: 8px 4px; }}
            #recentNavScroll {{ background: transparent; border: 0; }}
            #brandButton {{
                background: transparent;
                font-size: 20px;
                font-weight: 800;
                padding: 6px 10px;
                border: 0;
                border-radius: 11px;
                text-align: left;
            }}
            #brandButton:hover {{ background: {c['panel']}; }}
            #globalSearch {{
                background: {c['input']};
                border: 1px solid {c['border']};
                border-radius: 21px;
                padding: 9px 16px;
                font-size: 15px;
                selection-background-color: {c['blue']};
            }}
            #globalSearch:hover {{ border-color: #4a4a4a; }}
            #globalSearch:focus {{ border-color: #6a6a6a; }}
            #qualityButton, #languageButton, #settingsButton {{
                min-height: 36px;
                background: {c['panel']};
                border: 1px solid transparent;
            }}
            #qualityButton:hover, #languageButton:hover, #settingsButton:hover {{
                background: {c['panel2']};
            }}
            #qualityButton {{ min-width: 82px; }}
            #languageButton {{ min-width: 54px; font-weight: 750; }}
            #settingsButton {{ min-width: 40px; max-width: 40px; padding: 7px; }}

            /* ---------- general controls ---------- */
            QPushButton, QComboBox {{
                background: {c['panel2']};
                border: 1px solid transparent;
                border-radius: 18px;
                padding: 8px 14px;
            }}
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 18px;
                padding: 8px 10px;
            }}
            QPushButton:hover, QComboBox:hover {{
                background: {c['hover']};
                border-color: transparent;
            }}
            QToolButton:hover {{
                background: {c['panel2']};
                border-color: transparent;
            }}
            QPushButton:pressed, QToolButton:pressed {{
                background: {c['panel']};
            }}
            QPushButton:focus, QToolButton:focus, QComboBox:focus {{
                border-color: {c['blue']};
            }}
            QPushButton:checked {{
                background: {c['text']};
                color: {c['bg']};
                font-weight: 750;
            }}
            QComboBox {{
                padding-right: 26px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: 0;
                background: transparent;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: url("{(Path(__file__).resolve().parent / 'assets' / 'chevron-down.svg').as_posix()}");
                width: 10px;
                height: 10px;
            }}
            QToolButton {{ min-width: 38px; min-height: 36px; padding: 8px 10px; }}
            #playButton {{ min-width: 44px; min-height: 40px; }}
            #sidebarToggle {{
                min-width: 96px;
                padding-left: 12px;
                padding-right: 12px;
                font-weight: 650;
            }}
            #sidebarToggle[open="true"] {{
                background: {c['panel']};
            }}
            #sidebarClose {{
                background: transparent;
                min-width: 30px;
                max-width: 34px;
                border-color: transparent;
            }}
            #primaryButton, #ctaButton {{
                background: {c['accent']};
                color: white;
                font-weight: 760;
                border-radius: 18px;
                border: 1px solid transparent;
                padding: 9px 18px;
            }}
            #primaryButton:hover, #ctaButton:hover {{ background: #ff3355; }}
            #secondaryButton {{
                background: {c['panel2']};
            }}

            /* ---------- page typography ---------- */
            #pageHeading {{ font-size: 28px; font-weight: 800; }}
            #pageSubheading {{ color: {c['muted']}; font-size: 14px; margin-bottom: 3px; }}
            #sectionHeading {{ font-size: 20px; font-weight: 750; }}
            #sectionCount {{ color: {c['muted']}; font-size: 12px; }}
            #status, #muted, QLabel#muted {{ color: {c['muted']}; }}

            /* ---------- home ---------- */
            #homeHero, #searchEmpty {{
                background: {c['panel']};
                border: 1px solid {c['border']};
                border-radius: 16px;
                min-height: 190px;
            }}
            #emptyTitle {{ font-size: 25px; font-weight: 800; }}
            #emptyHint {{ color: {c['muted']}; font-size: 12px; padding-top: 4px; }}
            #homeCard {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 11px;
            }}
            #homeCard:hover {{
                background: {c['panel']};
                border-color: {c['border']};
            }}
            #homeTitle {{ font-weight: 700; font-size: 14px; }}
            #homeMeta {{ color: {c['muted']}; font-size: 12px; }}
            #imagePlaceholder {{
                background: {c['panel2']};
                color: {c['muted']};
                border-radius: 8px;
                font-size: 22px;
            }}
            #recommendationCard {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 11px;
            }}
            #recommendationCard:hover {{ background: {c['panel']}; border-color: {c['border']}; }}
            #recommendationTitle {{ font-weight: 700; font-size: 14px; }}
            #recommendationLoading, #homeHint {{
                background: {c['panel']};
                border: 1px solid {c['border']};
                border-radius: 12px;
            }}
            #libraryFolders {{ color: {c['muted']}; font-size: 13px; padding-bottom: 4px; }}
            #libraryEmpty {{
                background: {c['panel']};
                border: 1px solid {c['border']};
                border-radius: 14px;
                min-height: 180px;
            }}
            #localFileCard {{
                background: {c['panel']};
                border: 1px solid transparent;
                border-radius: 12px;
            }}
            #localFileCard:hover {{ background: {c['panel2']}; border-color: {c['border']}; }}
            #localPlayBadge {{
                background: {c['panel2']};
                border-radius: 22px;
                font-size: 15px;
                font-weight: 800;
            }}
            #localTitle {{ font-size: 15px; font-weight: 700; }}
            #localMeta {{ color: {c['muted']}; font-size: 12px; }}

            /* ---------- search ---------- */
            #searchCard {{
                background: {c['panel']};
                border-radius: 14px;
                border: 1px solid transparent;
            }}
            #searchCard:hover {{
                background: {c['panel2']};
                border-color: {c['border']};
            }}
            #resultTitle {{ font-size: 20px; font-weight: 750; }}
            #resultMeta {{ color: {c['muted']}; font-size: 13px; }}
            #resultCTA {{ color: {c['blue']}; font-weight: 700; font-size: 13px; }}

            /* ---------- player ---------- */
            #video {{ background: #000000; border-radius: 10px; }}
            #placeholder {{
                color: #8d8d8d;
                font-size: 17px;
                font-weight: 600;
                background: transparent;
            }}
            #loadingOverlay {{
                background: rgba(15,15,15,205);
                color: white;
                border: 1px solid rgba(255,255,255,35);
                border-radius: 14px;
                font-size: 14px;
                font-weight: 650;
                padding: 11px;
            }}
            #playerChrome {{
                background: transparent;
            }}
            #videoTitle {{ font-size: 20px; font-weight: 780; padding-top: 1px; }}
            #watchMeta {{ color: {c['muted']}; font-size: 13px; padding-bottom: 2px; }}
            #timeLabel {{ color: {c['muted']}; font-size: 12px; min-width: 36px; }}

            /* ---------- episode panel ---------- */
            #sidebar {{
                border-left: 1px solid {c['border']};
                background: {c['bg']};
            }}
            #sideTitle {{ font-size: 18px; font-weight: 780; padding: 2px 2px 2px 1px; }}
            #episodeSearch {{
                background: {c['input']};
                border: 1px solid {c['border']};
                border-radius: 16px;
                padding: 7px 11px;
                min-height: 26px;
            }}
            #episodeSearch:focus {{ border-color: {c['blue']}; }}
            QListWidget#episodeList {{ background: {c['bg']}; border: 0; outline: none; }}
            QListWidget#episodeList::item {{ background: transparent; border: 0; }}
            QListWidget#episodeList::item:selected {{ background: transparent; }}
            #episodeCard {{
                background: {c['panel']};
                border: 1px solid transparent;
                border-radius: 9px;
            }}
            #episodeCard[playing="true"] {{
                background: {c['panel2']};
                border-color: {c['accent']};
            }}
            #episodeTitle {{ font-weight: 720; font-size: 13px; }}
            #episodeMeta {{ color: {c['muted']}; font-size: 11px; }}
            #playingLabel {{
                color: white;
                background: {c['accent']};
                border-radius: 6px;
                padding: 2px 5px;
                font-size: 9px;
                font-weight: 850;
            }}

            /* ---------- sliders/progress ---------- */
            QSlider::groove:horizontal {{
                height: 4px;
                background: {c['border']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {c['text']};
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QProgressBar {{ background: {c['border']}; border: 0; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {c['accent']}; border-radius: 2px; }}
            QSplitter::handle {{ background: {c['border']}; width: 1px; }}
            QDialog {{
                background: {c['panel']};
                border: 1px solid {c['border']};
                border-radius: 16px;
            }}
            QDialog QComboBox {{
                min-height: 34px;
                border-radius: 12px;
                background: {c['input']};
                border: 1px solid {c['border']};
                padding-left: 12px;
            }}
            QDialog QLabel {{
                color: {c['text']};
            }}
            QCheckBox {{
                spacing: 9px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid {c['border']};
                background: {c['input']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {c['muted']};
            }}
            QCheckBox::indicator:checked {{
                background: {c['accent']};
                border-color: {c['accent']};
                image: url("{(Path(__file__).resolve().parent / 'assets' / 'check.svg').as_posix()}");
            }}
            #primaryButton {{
                min-width: 92px;
                background: {c['text']};
                color: {c['bg']};
            }}
            #primaryButton:hover {{ background: {c['muted']}; }}
            #secondaryButton {{
                min-width: 92px;
                background: transparent;
                border: 1px solid {c['border']};
            }}
            #secondaryButton:hover {{ background: {c['panel2']}; }}
            QMessageBox QPushButton {{
                min-width: 88px;
            }}

            /* ---------- scrolling ---------- */
            QMenu {{
                background: {c['panel']};
                color: {c['text']};
                border: 1px solid {c['border']};
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 22px 8px 12px;
                border-radius: 7px;
            }}
            QMenu::item:selected {{ background: {c['panel2']}; }}
            QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}

            QScrollArea {{ background: {c['bg']}; border: 0; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{
                background: {c['hover']};
                border-radius: 5px;
                min-height: 34px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ background: transparent; height: 9px; }}
            QScrollBar::handle:horizontal {{
                background: {c['hover']};
                border-radius: 4px;
                min-width: 36px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

    # --------------------------------------------------------------- busy/error
    def set_busy(self, text: str, use_cursor: bool = True) -> None:
        self.status.setText(text) if hasattr(self, "status") else None
        if use_cursor and not self.busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.busy = True

    def clear_busy(self) -> None:
        if self.busy:
            QApplication.restoreOverrideCursor()
            self.busy = False

    def show_error(self, message: str) -> None:
        self.clear_busy()
        self.hide_loading()
        if hasattr(self, "status"):
            self.status.setText(message)
        QMessageBox.warning(self, APP_NAME, message)

    # --------------------------------------------------------------- keyboard
    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Normal text editing must win while the search box has focus.
        if isinstance(QApplication.focusWidget(), QLineEdit) and event.key() not in {Qt.Key_Escape, Qt.Key_F11}:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key_Slash or (key == Qt.Key_F and event.modifiers() & Qt.ControlModifier):
            self.focus_search(); event.accept(); return
        if key == Qt.Key_H:
            self.go_home(); event.accept(); return
        if key == Qt.Key_E and self.pages.currentWidget() is self.watch_page:
            self.toggle_episode_sidebar(); event.accept(); return
        if key in {Qt.Key_Space, Qt.Key_K}:
            self.toggle_pause(); event.accept(); return
        if key == Qt.Key_J:
            self.seek_relative(-10); event.accept(); return
        if key == Qt.Key_L:
            self.seek_relative(10); event.accept(); return
        if key == Qt.Key_Left:
            self.seek_relative(-5); event.accept(); return
        if key == Qt.Key_Right:
            self.seek_relative(5); event.accept(); return
        if key == Qt.Key_Up:
            self.volume.setValue(min(130, self.volume.value() + 5)); event.accept(); return
        if key == Qt.Key_Down:
            self.volume.setValue(max(0, self.volume.value() - 5)); event.accept(); return
        if key in {Qt.Key_F, Qt.Key_F11}:
            self.toggle_fullscreen(); event.accept(); return
        if key == Qt.Key_Escape and self.isFullScreen():
            self.exit_fullscreen(); event.accept(); return
        if key == Qt.Key_M:
            self.toggle_mute(); event.accept(); return
        if key == Qt.Key_N:
            self.change_episode(1); event.accept(); return
        if key == Qt.Key_P:
            self.change_episode(-1); event.accept(); return
        digit_map = {
            Qt.Key_0: 0, Qt.Key_1: 10, Qt.Key_2: 20, Qt.Key_3: 30, Qt.Key_4: 40,
            Qt.Key_5: 50, Qt.Key_6: 60, Qt.Key_7: 70, Qt.Key_8: 80, Qt.Key_9: 90,
        }
        if key in digit_map:
            self.seek_percent(digit_map[key]); event.accept(); return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        try:
            pos = self.mpv.request(["get_property", "time-pos"])
            duration = self.mpv.request(["get_property", "duration"])
            path = self.mpv.request(["get_property", "path"])
            stream_matches = bool(self.current_stream and path == self.current_stream.get("url"))
            if stream_matches and pos is not None and duration:
                p, d = float(pos), float(duration)
                self.persist_progress(p, d, d > 30 and p >= d - 8, force_save=True)
        except Exception:
            pass
        self.state.save()
        self.mpv.shutdown()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("AniView")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
