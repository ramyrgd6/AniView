# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from state import APP_CACHE_DIR


class MPVController:
    def __init__(self, video_widget: QWidget):
        self.video_widget = video_widget
        self.proc: subprocess.Popen | None = None
        self.log_path: Path | None = None
        self.log_file = None
        self.socket_path = f"/tmp/aniview-mpv-{os.getpid()}.sock"

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        mpv = shutil.which("mpv")
        if not mpv:
            raise RuntimeError("mpv is not installed or is not in PATH.")

        wid = int(self.video_widget.winId())
        APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = APP_CACHE_DIR / "mpv.log"
        self.log_file = self.log_path.open("w", buffering=1)
        cmd = [
            mpv,
            "--no-config",
            f"--wid={wid}",
            f"--input-ipc-server={self.socket_path}",
            "--idle=yes",
            "--keep-open=yes",
            "--force-window=yes",
            "--osc=no",
            "--input-default-bindings=no",
            "--input-vo-keyboard=no",
            "--hwdec=auto",
            "--vo=gpu-next",
            "--gpu-api=opengl",
            "--gpu-context=x11egl",
            "--x11-wid-title=no",
            "--background=color",
            "--background-color=#000000",
            "--cache=yes",
            "--cache-pause=yes",
        ]
        env = os.environ.copy()
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("WAYLAND_SOCKET", None)
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.log_file, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 4
        while time.time() < deadline and not os.path.exists(self.socket_path):
            if self.proc.poll() is not None:
                self.log_file.flush()
                detail = self.log_path.read_text(errors="replace").strip()
                tail = "\n".join(detail.splitlines()[-10:])
                raise RuntimeError("mpv exited before AniView could connect." + (f"\n\n{tail}" if tail else ""))
            time.sleep(0.03)
        if not os.path.exists(self.socket_path):
            self.proc.terminate()
            raise RuntimeError("mpv started, but its control socket never appeared. See ~/.cache/aniview/mpv.log")

    def request(self, command: list, timeout: float = 0.35):
        if not os.path.exists(self.socket_path):
            return None
        payload = (json.dumps({"command": command}) + "\n").encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(self.socket_path)
                sock.sendall(payload)
                data = b""
                while b"\n" not in data:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    return None
                result = json.loads(data.split(b"\n", 1)[0].decode(errors="replace"))
                if result.get("error") == "success":
                    return result.get("data")
        except (OSError, json.JSONDecodeError):
            return None
        return None

    def command(self, command: list) -> None:
        self.request(command)

    def load(self, stream: dict, volume: int = 100) -> None:
        self.start()
        if stream.get("referrer"):
            self.command(["set_property", "referrer", stream["referrer"]])
        self.command(["set_property", "volume", int(volume)])
        self.command(["set_property", "force-media-title", stream.get("media_title", "AniView")])
        self.command(["loadfile", stream["url"], "replace"])
        subtitle = stream.get("subtitle")
        if subtitle:
            QTimer.singleShot(700, lambda: self.command(["sub-add", subtitle, "select"]))

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.command(["screenshot-to-file", str(path), "video"])

    def shutdown(self) -> None:
        try:
            self.command(["quit"])
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
