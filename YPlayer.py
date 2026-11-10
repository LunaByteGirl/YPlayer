#!/usr/bin/env python3
"""
=============================================================================
 YPlayer - Minimalistischer Nativer YouTube & YouTube Music Player
=============================================================================
Features:
  - Neuer Home-Bildschirm als Standard-Startseite
  - Keine automatische Charts-Suche beim Start
  - Stabiles lokales Audio-Caching (keine Verbindungsabbrüche mehr)
  - Nahtlose Hintergrund-Pufferung des nächsten Titels
  - Google-Konto-Integration (Playlists, Alben, Lieblingslieder)
  - Ästhetisches, dunkles Studio-Design (Obsidian/Graphit & Cyan-Akzente)
  - Vektor-Schaltflächen (QtSvg) - keine Emojis
"""

import sys
import os

# -----------------------------------------------------------------------------
# Automatisch in das YPlayer-Venv wechseln (nur wenn nicht als AppImage/Frozen gebaut)
# -----------------------------------------------------------------------------
if not getattr(sys, "frozen", False):
    VENV_DIR = os.path.expanduser("~/.local/share/yplayer/venv")
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")
    if sys.prefix != VENV_DIR and os.path.exists(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import json
import re
import datetime
import time
import socket
import struct
import uuid
import threading
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

# PyQt6 & QtSvg Imports
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QUrl, QSize, QRunnable, QThreadPool, QByteArray
)
from PyQt6.QtGui import (
    QPixmap, QImage, QFont, QKeySequence, QShortcut, QIcon, QPainter, QPainterPath
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QSizePolicy, QMessageBox, QScrollArea, QGridLayout
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# yt-dlp & ytmusicapi
import yt_dlp
from yt_dlp.cookies import extract_cookies_from_browser
from ytmusicapi.auth.browser import sapisid_from_cookie, get_authorization, YTM_DOMAIN, initialize_headers
from ytmusicapi import YTMusic

# -----------------------------------------------------------------------------
# Pfade & Verzeichnisse (Plattformübergreifend Linux & Windows)
# -----------------------------------------------------------------------------
if sys.platform == "win32":
    DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "YPlayer"
    CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "YPlayer" / "cache"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "yplayer"
    CACHE_DIR = Path.home() / ".cache" / "yplayer"

CACHE_THUMBS = CACHE_DIR / "thumbs"
CACHE_AUDIO = CACHE_DIR / "audio"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_THUMBS.mkdir(parents=True, exist_ok=True)
CACHE_AUDIO.mkdir(parents=True, exist_ok=True)

FAVORITES_FILE = DATA_DIR / "favorites.json"
HISTORY_FILE = DATA_DIR / "history.json"
SESSION_FILE = DATA_DIR / "google_session.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DISCORD_SESSION_FILE = DATA_DIR / "discord_session.json"

DISCORD_CLIENT_ID = "1474703271959465994"

# -----------------------------------------------------------------------------
# Seiten-Indizes für QStackedWidget
# -----------------------------------------------------------------------------
PAGE_HOME = 0
PAGE_SEARCH = 1
PAGE_PLAYLISTS = 2
PAGE_PLAYLIST_DETAIL = 3
PAGE_ALBUMS = 4
PAGE_ALBUM_DETAIL = 5
PAGE_LIKED = 6
PAGE_QUEUE = 7
PAGE_FAVORITES = 8
PAGE_HISTORY = 9
PAGE_DISCORD_LOGIN = 10


def load_json(filepath, default_value):
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_value


def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[YPlayer] Fehler beim Speichern: {e}")


def load_discord_session():
    if DISCORD_SESSION_FILE.exists():
        try:
            with open(DISCORD_SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and "id" in data and "username" in data:
                    return data
        except Exception:
            pass
    return None


def save_discord_session(user_data):
    try:
        with open(DISCORD_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[YPlayer] Fehler beim Speichern der Discord-Sitzung: {e}")


def clear_discord_session():
    try:
        if DISCORD_SESSION_FILE.exists():
            DISCORD_SESSION_FILE.unlink()
    except Exception as e:
        print(f"[YPlayer] Fehler beim Löschen der Discord-Sitzung: {e}")


def make_circular_pixmap(pixmap, size=36):
    if not pixmap or pixmap.isNull():
        return None
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return rounded


def download_discord_avatar(user_id, avatar_hash):
    if not user_id:
        return None
    cache_path = CACHE_THUMBS / f"discord_avatar_{user_id}.png"
    if avatar_hash:
        url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128"
    else:
        try:
            disc = int(user_id) % 5
        except Exception:
            disc = 0
        url = f"https://cdn.discordapp.com/embed/avatars/{disc}.png"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = resp.read()
            cache_path.write_bytes(data)
            return str(cache_path)
    except Exception as e:
        print(f"[YPlayer] Discord-Avatar Download fehlgeschlagen: {e}")
        if cache_path.exists():
            return str(cache_path)
        return None


def format_duration(seconds):
    if not seconds:
        return "--:--"
    try:
        s = int(seconds)
        m = s // 60
        sec = s % 60
        if m >= 60:
            h = m // 60
            m = m % 60
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"
    except Exception:
        return "--:--"


# -----------------------------------------------------------------------------
# Vektor-Icon Factory (Pixelperfekte Vektoren ohne Emojis)
# -----------------------------------------------------------------------------
class IconFactory:
    @staticmethod
    def create(svg_body, size=24, viewBox="0 0 24 24"):
        full_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewBox}">{svg_body}</svg>'
        renderer = QSvgRenderer(QByteArray(full_svg.encode("utf-8")))
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        return QIcon(pix)

    @classmethod
    def play(cls, color="#090a0f", size=24):
        return cls.create(f'<polygon points="7,4 20,12 7,20 7,4" fill="{color}"/>', size)

    @classmethod
    def pause(cls, color="#090a0f", size=24):
        return cls.create(f'<rect x="6" y="4" width="4" height="16" rx="1.5" fill="{color}"/><rect x="14" y="4" width="4" height="16" rx="1.5" fill="{color}"/>', size)

    @classmethod
    def prev(cls, color="#94a3b8", size=24):
        return cls.create(f'<polygon points="19,20 9,12 19,4 19,20" fill="{color}"/><line x1="5" y1="19" x2="5" y2="5" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>', size)

    @classmethod
    def next(cls, color="#94a3b8", size=24):
        return cls.create(f'<polygon points="5,4 15,12 5,20 5,4" fill="{color}"/><line x1="19" y1="5" x2="19" y2="19" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>', size)

    @classmethod
    def shuffle(cls, color="#94a3b8", size=24):
        return cls.create(
            f'<polyline points="16 3 21 3 21 8" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<line x1="4" y1="20" x2="21" y2="3" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<polyline points="21 16 21 21 16 21" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<line x1="15" y1="15" x2="21" y2="21" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="4" y1="4" x2="9" y2="9" stroke="{color}" stroke-width="2" stroke-linecap="round"/>', size
        )

    @classmethod
    def repeat(cls, color="#94a3b8", size=24, one=False):
        badge = f'<text x="12" y="15" font-size="8" font-weight="bold" fill="{color}" text-anchor="middle">1</text>' if one else ""
        return cls.create(
            f'<polyline points="17 1 21 5 17 9" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<path d="M3 11V9a4 4 0 0 1 4-4h14" stroke="{color}" stroke-width="2" stroke-linecap="round" fill="none"/>'
            f'<polyline points="7 23 3 19 7 15" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<path d="M21 13v2a4 4 0 0 1-4 4H3" stroke="{color}" stroke-width="2" stroke-linecap="round" fill="none"/>'
            f'{badge}', size
        )

    @classmethod
    def heart(cls, filled=False, color="#94a3b8", size=24):
        if filled:
            return cls.create(f'<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>', size)
        return cls.create(f'<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>', size)

    @classmethod
    def volume(cls, muted=False, color="#94a3b8", size=24):
        if muted:
            return cls.create(f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="{color}" stroke="{color}" stroke-width="1.5"/><line x1="23" y1="9" x2="17" y2="15" stroke="#ef4444" stroke-width="2" stroke-linecap="round"/><line x1="17" y1="9" x2="23" y2="15" stroke="#ef4444" stroke-width="2" stroke-linecap="round"/>', size)
        return cls.create(f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="{color}" stroke="{color}" stroke-width="1.5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07" stroke="{color}" stroke-width="2" stroke-linecap="round" fill="none"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14" stroke="{color}" stroke-width="2" stroke-linecap="round" fill="none"/>', size)

    @classmethod
    def plus(cls, color="#94a3b8", size=20):
        return cls.create(f'<line x1="12" y1="5" x2="12" y2="19" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="5" y1="12" x2="19" y2="12" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>', size)

    @classmethod
    def trash(cls, color="#94a3b8", size=20):
        return cls.create(f'<polyline points="3 6 5 6 21 6" stroke="{color}" stroke-width="2" stroke-linecap="round" fill="none"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>', size)

    @classmethod
    def arrow_left(cls, color="#94a3b8", size=20):
        return cls.create(f'<line x1="19" y1="12" x2="5" y2="12" stroke="{color}" stroke-width="2" stroke-linecap="round"/><polyline points="12 19 5 12 12 5" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>', size)

    @classmethod
    def home(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<path d="M3 9.5L12 3l9 6.5v11a1.5 1.5 0 0 1-1.5 1.5H4.5A1.5 1.5 0 0 1 3 20.5v-11z" stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M9 22V12h6v10" stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>', size
        )

    @classmethod
    def search(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<circle cx="11" cy="11" r="7" stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round"/>'
            f'<line x1="21" y1="21" x2="16.5" y2="16.5" stroke="{color}" stroke-width="2" stroke-linecap="round"/>', size
        )

    @classmethod
    def playlist(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<line x1="8" y1="6" x2="21" y2="6" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="8" y1="12" x2="21" y2="12" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="8" y1="18" x2="15" y2="18" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<circle cx="4" cy="6" r="1.5" fill="{color}"/>'
            f'<circle cx="4" cy="12" r="1.5" fill="{color}"/>'
            f'<circle cx="4" cy="18" r="1.5" fill="{color}"/>', size
        )

    @classmethod
    def disc(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<circle cx="12" cy="12" r="9" stroke="{color}" stroke-width="2" fill="none"/>'
            f'<circle cx="12" cy="12" r="3" stroke="{color}" stroke-width="2" fill="none"/>', size
        )

    @classmethod
    def queue(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<line x1="4" y1="6" x2="14" y2="6" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="4" y1="12" x2="11" y2="12" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<line x1="4" y1="18" x2="13" y2="18" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
            f'<polygon points="16,10 21,13.5 16,17" fill="{color}"/>', size
        )

    @classmethod
    def history(cls, color="#94a3b8", size=20):
        return cls.create(
            f'<circle cx="12" cy="12" r="9" stroke="{color}" stroke-width="2" fill="none"/>'
            f'<polyline points="12 7 12 12 15 14" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>', size
        )

    @classmethod
    def check(cls, color="#38bdf8", size=16):
        return cls.create(
            f'<polyline points="20 6 9 17 4 12" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>', size
        )

    @classmethod
    def discord(cls, color="#5865f2", size=20):
        return cls.create(
            f'<path fill="{color}" d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>', size
        )


# -----------------------------------------------------------------------------
# Klickbare Karte (für Home-Dashboard)
# -----------------------------------------------------------------------------
class ClickableCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)


# -----------------------------------------------------------------------------
# Google / YouTube Music Authentifizierung
# -----------------------------------------------------------------------------
def build_ytmusic_from_cookies():
    try:
        jar = extract_cookies_from_browser("firefox")
        yt_cookies = [c for c in jar if "youtube" in c.domain]
        if not yt_cookies:
            return None, "Keine YouTube-Cookies in Firefox gefunden."

        cookie_str = "; ".join([f"{c.name}={c.value}" for c in yt_cookies])
        sapisid = sapisid_from_cookie(cookie_str)
        if not sapisid:
            return None, "Kein gültiger Google-Sitzungsschlüssel gefunden."

        headers = initialize_headers()
        headers["cookie"] = cookie_str
        headers["authorization"] = get_authorization(f"{sapisid} {YTM_DOMAIN}")
        headers["x-goog-authuser"] = "0"

        headers_dict = dict(headers)
        save_json(SESSION_FILE, headers_dict)
        return YTMusic(headers_dict), None
    except Exception as e:
        return None, str(e)


def build_ytmusic_from_saved():
    if not SESSION_FILE.exists():
        return None
    try:
        headers = load_json(SESSION_FILE, {})
        if headers:
            cookie_str = headers.get("cookie", "")
            if cookie_str:
                sapisid = sapisid_from_cookie(cookie_str)
                if sapisid:
                    headers["authorization"] = get_authorization(f"{sapisid} {YTM_DOMAIN}")
            return YTMusic(headers)
    except Exception:
        pass
    return None


# -----------------------------------------------------------------------------
# Audio-Cache & Download Engine
# -----------------------------------------------------------------------------
def get_cached_audio_path(track_id):
    clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', track_id)
    matches = list(CACHE_AUDIO.glob(f"{clean_id}.*"))
    for m in matches:
        if m.is_file() and m.stat().st_size > 100 * 1024:
            return str(m)
    return None


class AudioDownloadWorker(QThread):
    ready = pyqtSignal(dict, str)
    error = pyqtSignal(str)

    def __init__(self, track):
        super().__init__()
        self.track = track

    def run(self):
        track_id = self.track.get("id")
        if not track_id:
            self.error.emit("Ungültige Titel-ID")
            return

        cached = get_cached_audio_path(track_id)
        if cached:
            self.ready.emit(self.track, cached)
            return

        try:
            clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', track_id)
            outtmpl = str(CACHE_AUDIO / f"{clean_id}.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={track_id}"])

            downloaded = get_cached_audio_path(track_id)
            if downloaded:
                self.ready.emit(self.track, downloaded)
            else:
                self.error.emit("Audio konnte nicht heruntergeladen werden")
        except Exception as e:
            self.error.emit(str(e))


class PrefetchWorker(QRunnable):
    def __init__(self, track_id):
        super().__init__()
        self.track_id = track_id

    def run(self):
        if not self.track_id or get_cached_audio_path(self.track_id):
            return
        try:
            clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', self.track_id)
            outtmpl = str(CACHE_AUDIO / f"{clean_id}.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={self.track_id}"])
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Weitere Asynchrone Worker
# -----------------------------------------------------------------------------
class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query, limit=20):
        super().__init__()
        self.query = query.strip()
        self.limit = limit

    def run(self):
        try:
            url_match = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", self.query)
            target = f"https://www.youtube.com/watch?v={url_match.group(1)}" if url_match else f"ytsearch{self.limit}:{self.query}"

            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target, download=False)
                results = []

                if "entries" in info:
                    for entry in info["entries"]:
                        if not entry or not entry.get("id"):
                            continue
                        dur = entry.get("duration") or 0
                        results.append({
                            "id": entry.get("id"),
                            "title": entry.get("title", "Unbekannter Titel"),
                            "uploader": entry.get("uploader") or entry.get("channel") or "Unbekannter Interpret",
                            "duration": format_duration(dur),
                            "duration_sec": dur,
                            "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg"
                        })
                else:
                    dur = info.get("duration") or 0
                    results.append({
                        "id": info.get("id"),
                        "title": info.get("title", "Unbekannter Titel"),
                        "uploader": info.get("uploader") or info.get("channel") or "Unbekannter Interpret",
                        "duration": format_duration(dur),
                        "duration_sec": dur,
                        "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{info.get('id')}/hqdefault.jpg"
                    })

                self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class GoogleLoginWorker(QThread):
    finished = pyqtSignal(bool, str)

    def run(self):
        yt, err = build_ytmusic_from_cookies()
        if yt:
            self.finished.emit(True, "Erfolgreich mit Google angemeldet")
        else:
            self.finished.emit(False, err or "Anmeldung fehlgeschlagen")


class PlaylistsWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, yt_instance):
        super().__init__()
        self.yt = yt_instance

    def run(self):
        try:
            playlists = self.yt.get_library_playlists(limit=50)
            self.finished.emit(playlists)
        except Exception as e:
            self.error.emit(str(e))


class PlaylistTracksWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, yt_instance, playlist_id):
        super().__init__()
        self.yt = yt_instance
        self.playlist_id = playlist_id

    def run(self):
        try:
            data = self.yt.get_playlist(self.playlist_id, limit=200)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class AlbumsWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, yt_instance):
        super().__init__()
        self.yt = yt_instance

    def run(self):
        try:
            albums = self.yt.get_library_albums(limit=50)
            self.finished.emit(albums)
        except Exception as e:
            self.error.emit(str(e))


class AlbumTracksWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, yt_instance, browse_id):
        super().__init__()
        self.yt = yt_instance
        self.browse_id = browse_id

    def run(self):
        try:
            data = self.yt.get_album(self.browse_id)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class LikedSongsWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, yt_instance):
        super().__init__()
        self.yt = yt_instance

    def run(self):
        try:
            data = self.yt.get_liked_songs(limit=200)
            tracks = data.get("tracks", [])
            self.finished.emit(tracks)
        except Exception as e:
            self.error.emit(str(e))


class ThumbnailLoader(QRunnable):
    def __init__(self, url, track_id, callback):
        super().__init__()
        self.url = url
        self.track_id = track_id
        self.callback = callback

    def run(self):
        if not self.track_id:
            return
        clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', self.track_id)
        cache_file = CACHE_THUMBS / f"{clean_id}.jpg"
        data = None

        if cache_file.exists():
            try:
                data = cache_file.read_bytes()
            except Exception:
                pass

        if not data and self.url:
            try:
                req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = resp.read()
                    cache_file.write_bytes(data)
            except Exception:
                pass

        if data:
            self.callback(self.track_id, data)


# -----------------------------------------------------------------------------
# Discord Socket & Process Helpers (Plattformübergreifend Linux & Windows)
# -----------------------------------------------------------------------------
class DiscordIPCConnection:
    def __init__(self, path):
        self.path = path
        self.is_win = (sys.platform == "win32")
        if self.is_win:
            self.handle = open(path, "r+b", buffering=0)
        else:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)
            self.sock.connect(path)

    def sendall(self, data):
        if self.is_win:
            self.handle.write(data)
            self.handle.flush()
        else:
            self.sock.sendall(data)

    def recv(self, size):
        if self.is_win:
            return self.handle.read(size)
        else:
            return self.sock.recv(size)

    def close(self):
        try:
            if self.is_win:
                self.handle.close()
            else:
                self.sock.close()
        except Exception:
            pass


def find_discord_socket():
    if sys.platform == "win32":
        for i in range(10):
            pipe_name = rf"\\.\pipe\discord-ipc-{i}"
            if os.path.exists(pipe_name):
                return pipe_name
        return None

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    candidates = []
    for i in range(10):
        candidates.append(os.path.join(runtime_dir, f"discord-ipc-{i}"))
        candidates.append(os.path.join(runtime_dir, "app", "com.discordapp.Discord", f"discord-ipc-{i}"))
        candidates.append(os.path.expanduser(f"~/.var/app/com.discordapp.Discord/sandbox/discord-ipc-{i}"))
        candidates.append(os.path.join(runtime_dir, "app", "dev.vencord.Vesktop", f"discord-ipc-{i}"))
        candidates.append(os.path.join(runtime_dir, "app", "io.github.spacingbat3.webcord", f"discord-ipc-{i}"))
        candidates.append(f"/tmp/discord-ipc-{i}")

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def launch_discord_app():
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        discord_exe = os.path.join(local_app, "Discord", "Update.exe")
        if os.path.exists(discord_exe):
            try:
                subprocess.Popen([discord_exe, "--processStart", "Discord.exe"])
                return True
            except Exception:
                pass
        try:
            os.startfile("discord:")
            return True
        except Exception:
            pass
        return False

    try:
        res = subprocess.run(["which", "flatpak"], capture_output=True, text=True)
        if res.returncode == 0:
            subprocess.Popen(
                ["flatpak", "run", "com.discordapp.Discord"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["discord"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        pass

    return False


class DiscordLoginWorker(QThread):
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, client_id=DISCORD_CLIENT_ID):
        super().__init__()
        self.client_id = str(client_id)

    def run(self):
        self.status_updated.emit("Suche nach aktiver Discord-Instanz...")
        sock_path = find_discord_socket()

        if not sock_path:
            self.status_updated.emit("Discord ist nicht gestartet. Starte Discord Desktop-App...")
            launched = launch_discord_app()
            if not launched:
                self.finished.emit(False, {}, "Discord konnte nicht automatisch gestartet werden. Bitte starte Discord manuell.")
                return

            start_t = time.time()
            while time.time() - start_t < 14.0:
                time.sleep(0.6)
                sock_path = find_discord_socket()
                if sock_path:
                    break

        if not sock_path:
            self.finished.emit(False, {}, "Keine aktive Discord-Instanz gefunden. Bitte öffne Discord und versuche es erneut.")
            return

        self.status_updated.emit("Verbinde mit lokalem Discord IPC-Socket...")
        try:
            sock = DiscordIPCConnection(sock_path)

            payload = json.dumps({"v": 1, "client_id": self.client_id}).encode("utf-8")
            sock.sendall(struct.pack("<II", 0, len(payload)) + payload)

            header = sock.recv(8)
            if len(header) == 8:
                op, length = struct.unpack("<II", header)
                data = sock.recv(length)
                resp = json.loads(data.decode("utf-8"))
                if resp.get("evt") == "READY":
                    user = resp.get("data", {}).get("user", {})
                    sock.close()
                    if user:
                        name = user.get("global_name") or user.get("username", "Benutzer")
                        self.status_updated.emit(f"Angemeldet als {name}. Lade Avatar...")
                        uid = user.get("id")
                        av = user.get("avatar")
                        av_path = download_discord_avatar(uid, av)
                        if av_path:
                            user["avatar_path"] = av_path
                        user["logged_in_at"] = int(time.time())
                        save_discord_session(user)
                        self.finished.emit(True, user, f"Erfolgreich als {name} angemeldet!")
                        return

            sock.close()
            self.finished.emit(False, {}, "Ungültige Antwort beim Discord-Handshake.")
        except Exception as e:
            self.finished.emit(False, {}, f"Verbindungsfehler zu Discord: {e}")


# -----------------------------------------------------------------------------
# Discord Rich Presence Engine (Asynchron, Thread-Safe & Robust)
# -----------------------------------------------------------------------------
class DiscordRPCWorker(QThread):
    connection_changed = pyqtSignal(bool)
    user_authenticated = pyqtSignal(dict)

    def __init__(self, client_id=DISCORD_CLIENT_ID):
        super().__init__()
        self.client_id = str(client_id)
        self.enabled = True
        self.running = True
        self.sock = None
        self.is_connected = False
        self.current_activity = None
        self._lock = threading.Lock()
        self._wake_event = threading.Event()

    def set_enabled(self, enabled):
        with self._lock:
            self.enabled = enabled
        self._wake_event.set()

    def update_track(self, track, is_playing, position_ms=0, duration_ms=0):
        if not track:
            self.clear_track()
            return

        title = track.get("title", "Unbekannter Titel")[:128]
        artist = track.get("uploader", "Unbekannter Interpret")[:128]
        track_id = track.get("id", "")
        thumb = track.get("thumbnail", "")

        now = int(time.time())
        pos_sec = max(0, int(position_ms / 1000.0))
        dur_sec = max(0, int(duration_ms / 1000.0))

        activity = {
            "details": title,
            "assets": {
                "large_image": thumb if (thumb and thumb.startswith("http")) else "youtube_music",
                "large_text": "YPlayer",
            }
        }

        if track_id:
            activity["buttons"] = [
                {"label": "Auf YouTube anhören", "url": f"https://www.youtube.com/watch?v={track_id}"}
            ]

        if is_playing:
            activity["state"] = f"von {artist}" if artist else "YPlayer"
            activity["assets"]["small_image"] = "play"
            activity["assets"]["small_text"] = "Wiedergabe"
            start_ts = now - pos_sec
            activity["timestamps"] = {"start": start_ts}
            if dur_sec > 0:
                activity["timestamps"]["end"] = start_ts + dur_sec
        else:
            activity["state"] = f"Pausiert • {artist}"
            activity["assets"]["small_image"] = "pause"
            activity["assets"]["small_text"] = "Pausiert"

        with self._lock:
            self.current_activity = activity
        self._wake_event.set()

    def clear_track(self):
        with self._lock:
            self.current_activity = None
        self._wake_event.set()

    def stop(self):
        self.running = False
        self._wake_event.set()
        self.wait(1500)

    def run(self):
        last_sent_activity = None
        last_connect_attempt = 0

        while self.running:
            now = time.time()

            if not self.enabled:
                if self.is_connected:
                    self._clear_activity()
                    self._disconnect()
                self._wake_event.wait(timeout=3.0)
                self._wake_event.clear()
                continue

            # Check / establish connection if needed
            if not self.is_connected:
                if now - last_connect_attempt >= 4.0:
                    last_connect_attempt = now
                    if self._find_and_connect():
                        last_sent_activity = None

            # Send activity if connected
            if self.is_connected:
                with self._lock:
                    target_activity = self.current_activity

                # Send if activity changed
                if target_activity != last_sent_activity:
                    if target_activity:
                        success = self._send_activity(target_activity)
                    else:
                        success = self._clear_activity()
                    if success:
                        last_sent_activity = target_activity
                    else:
                        self._disconnect()
                        last_sent_activity = None

            self._wake_event.wait(timeout=4.0)
            self._wake_event.clear()

        # Clean exit on shutdown
        if self.is_connected:
            self._clear_activity()
            self._disconnect()

    def _find_and_connect(self):
        path = find_discord_socket()
        if path:
            return self._connect(path)
        return False

    def _connect(self, path):
        try:
            self.sock = DiscordIPCConnection(path)

            # Handshake
            payload = json.dumps({"v": 1, "client_id": self.client_id}).encode("utf-8")
            self.sock.sendall(struct.pack("<II", 0, len(payload)) + payload)

            # Read response
            header = self.sock.recv(8)
            if len(header) == 8:
                op, length = struct.unpack("<II", header)
                data = self.sock.recv(length)
                resp = json.loads(data.decode("utf-8"))
                if resp.get("evt") == "READY":
                    self.is_connected = True
                    user = resp.get("data", {}).get("user", {})
                    if user:
                        self.user_authenticated.emit(user)
                    self.connection_changed.emit(True)
                    return True
            self._disconnect()
            return False
        except Exception:
            self._disconnect()
            return False

    def _send_activity(self, activity):
        if not self.sock or not self.is_connected:
            return False
        try:
            req = {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": activity
                },
                "nonce": str(uuid.uuid4())
            }
            payload = json.dumps(req).encode("utf-8")
            self.sock.sendall(struct.pack("<II", 1, len(payload)) + payload)
            header = self.sock.recv(8)
            if len(header) == 8:
                op, length = struct.unpack("<II", header)
                self.sock.recv(length)
            return True
        except Exception:
            return False

    def _clear_activity(self):
        if not self.sock or not self.is_connected:
            return False
        try:
            req = {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": None
                },
                "nonce": str(uuid.uuid4())
            }
            payload = json.dumps(req).encode("utf-8")
            self.sock.sendall(struct.pack("<II", 1, len(payload)) + payload)
            header = self.sock.recv(8)
            if len(header) == 8:
                op, length = struct.unpack("<II", header)
                self.sock.recv(length)
            return True
        except Exception:
            return False

    def _disconnect(self):
        was_connected = self.is_connected
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if was_connected:
            self.connection_changed.emit(False)


# -----------------------------------------------------------------------------
# Track-Zeile
# -----------------------------------------------------------------------------
class TrackRowWidget(QWidget):
    play_requested = pyqtSignal(dict)
    queue_requested = pyqtSignal(dict)
    fav_requested = pyqtSignal(dict)
    remove_requested = pyqtSignal(dict)

    def __init__(self, track, is_queue=False, is_playing=False, is_fav=False):
        super().__init__()
        self.track = track
        self.is_queue = is_queue
        self.is_playing = is_playing
        self.is_fav = is_fav
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(14)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(58, 36)
        self.thumb_label.setStyleSheet("background-color: #141720; border: 1px solid #1f232f; border-radius: 6px;")
        self.thumb_label.setScaledContents(True)
        layout.addWidget(self.thumb_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_color = "#38bdf8" if self.is_playing else "#f8fafc"
        self.title_lbl = QLabel(self.track.get("title", ""))
        self.title_lbl.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {title_color};")
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title_lbl.setWordWrap(False)

        self.artist_lbl = QLabel(self.track.get("uploader", ""))
        self.artist_lbl.setStyleSheet("font-size: 11px; color: #8e99ac;")

        info_layout.addWidget(self.title_lbl)
        info_layout.addWidget(self.artist_lbl)
        layout.addLayout(info_layout, 1)

        dur_lbl = QLabel(self.track.get("duration", "--:--"))
        dur_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-family: monospace;")
        dur_lbl.setFixedWidth(52)
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(dur_lbl)

        self.play_btn = QPushButton()
        self.play_btn.setObjectName("btn_row_play")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setIcon(IconFactory.play("#f8fafc", 16))
        self.play_btn.setIconSize(QSize(14, 14))
        self.play_btn.setToolTip("Abspielen")
        self.play_btn.clicked.connect(lambda: self.play_requested.emit(self.track))
        layout.addWidget(self.play_btn)

        if not self.is_queue:
            self.queue_btn = QPushButton()
            self.queue_btn.setObjectName("btn_row_icon")
            self.queue_btn.setFixedSize(32, 32)
            self.queue_btn.setIcon(IconFactory.plus("#8e99ac", 16))
            self.queue_btn.setIconSize(QSize(14, 14))
            self.queue_btn.setToolTip("Zur Warteschlange hinzufügen")
            self.queue_btn.clicked.connect(lambda: self.queue_requested.emit(self.track))
            layout.addWidget(self.queue_btn)

            self.fav_btn = QPushButton()
            self.fav_btn.setObjectName("btn_row_icon")
            self.fav_btn.setFixedSize(32, 32)
            self.update_fav_icon(self.is_fav)
            self.fav_btn.setToolTip("Favorit")
            self.fav_btn.clicked.connect(lambda: self.fav_requested.emit(self.track))
            layout.addWidget(self.fav_btn)
        else:
            self.del_btn = QPushButton()
            self.del_btn.setObjectName("btn_row_icon")
            self.del_btn.setFixedSize(32, 32)
            self.del_btn.setIcon(IconFactory.trash("#8e99ac", 16))
            self.del_btn.setIconSize(QSize(14, 14))
            self.del_btn.setToolTip("Aus Warteschlange entfernen")
            self.del_btn.clicked.connect(lambda: self.remove_requested.emit(self.track))
            layout.addWidget(self.del_btn)

    def update_fav_icon(self, is_fav):
        self.is_fav = is_fav
        if self.is_fav:
            self.fav_btn.setIcon(IconFactory.heart(filled=True, color="#38bdf8", size=16))
            self.fav_btn.setStyleSheet("border-color: #38bdf8; background-color: rgba(56, 189, 248, 0.12);")
        else:
            self.fav_btn.setIcon(IconFactory.heart(filled=False, color="#8e99ac", size=16))
            self.fav_btn.setStyleSheet("")

    def set_thumbnail(self, pixmap):
        self.thumb_label.setPixmap(pixmap)


# -----------------------------------------------------------------------------
# Hauptfenster
# -----------------------------------------------------------------------------
class YPlayerWindow(QMainWindow):
    thumb_loaded_signal = pyqtSignal(str, bytes)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YPlayer")
        self.resize(1160, 760)
        self.setMinimumSize(960, 640)

        # State
        self.queue = []
        self.current_index = -1
        self.favorites = load_json(FAVORITES_FILE, [])
        self.history = load_json(HISTORY_FILE, [])
        self.repeat_mode = "off"
        self.is_shuffle = False
        self.is_seeking = False
        self.cached_pixmaps = {}

        # Google / YTMusic Instanz
        self.yt_instance = build_ytmusic_from_saved()

        # Audio-Engine
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)

        # Threading
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)
        self.thumb_loaded_signal.connect(self.on_thumb_loaded)

        self.search_worker = None
        self.download_worker = None

        # Einstellungen
        self.settings = load_json(SETTINGS_FILE, {"discord_rpc": True})
        self.discord_user = load_discord_session()

        # Discord Rich Presence Engine
        self.discord_worker = DiscordRPCWorker()
        self.discord_worker.set_enabled(self.settings.get("discord_rpc", True))
        self.discord_worker.connection_changed.connect(self.on_discord_connection_changed)
        self.discord_worker.user_authenticated.connect(self.on_discord_user_authenticated)
        self.discord_worker.start()

        self.init_ui()
        self.apply_theme()
        self.setup_shortcuts()
        self.update_google_status_ui()
        self.update_discord_account_ui()

        # Start auf dem Home-Bildschirm oder Discord-Login falls nicht angemeldet
        if self.discord_user:
            self.switch_view(PAGE_HOME)
        else:
            self.switch_view(PAGE_DISCORD_LOGIN)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        split_layout = QHBoxLayout()
        split_layout.setSpacing(0)

        # =====================================================================
        # 1. Sidebar (Minimalistisches Studio-Design)
        # =====================================================================
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(18, 22, 18, 18)
        sb_layout.setSpacing(8)

        logo_box = QHBoxLayout()
        logo_box.setSpacing(6)
        brand_lbl = QLabel("YPLAYER")
        brand_lbl.setObjectName("brand_label")
        dot_lbl = QLabel("●")
        dot_lbl.setStyleSheet("color: #38bdf8; font-size: 14px;")
        logo_box.addWidget(brand_lbl)
        logo_box.addWidget(dot_lbl)
        logo_box.addStretch()
        sb_layout.addLayout(logo_box)
        sb_layout.addSpacing(10)

        # Google Account Status-Karte
        account_card = QFrame()
        account_card.setObjectName("account_card")
        ac_layout = QVBoxLayout(account_card)
        ac_layout.setContentsMargins(12, 10, 12, 10)
        ac_layout.setSpacing(6)

        self.lbl_google_status = QLabel("GOOGLE: VERBUNDEN")
        self.lbl_google_status.setObjectName("status_indicator")
        ac_layout.addWidget(self.lbl_google_status)

        self.btn_google_auth = QPushButton("KONTO TRENNEN")
        self.btn_google_auth.setObjectName("btn_account_action")
        self.btn_google_auth.clicked.connect(self.handle_google_auth)
        ac_layout.addWidget(self.btn_google_auth)
        sb_layout.addWidget(account_card)

        # Discord Account & Rich Presence Status-Karte
        self.discord_card = QFrame()
        self.discord_card.setObjectName("discord_card")
        dc_layout = QVBoxLayout(self.discord_card)
        dc_layout.setContentsMargins(12, 10, 12, 10)
        dc_layout.setSpacing(6)

        dc_top = QHBoxLayout()
        dc_top.setSpacing(8)

        self.discord_avatar_lbl = QLabel()
        self.discord_avatar_lbl.setFixedSize(32, 32)
        self.discord_avatar_lbl.setStyleSheet("background-color: #1a1e2b; border: 1px solid #282e40; border-radius: 16px;")
        self.discord_avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc_top.addWidget(self.discord_avatar_lbl)

        dc_names = QVBoxLayout()
        dc_names.setSpacing(1)

        self.lbl_discord_username = QLabel("DISCORD KONTO")
        self.lbl_discord_username.setStyleSheet("font-size: 11px; font-weight: 700; color: #f8fafc;")

        self.lbl_discord_handle = QLabel("Nicht angemeldet")
        self.lbl_discord_handle.setStyleSheet("font-size: 10px; color: #8e99ac;")

        dc_names.addWidget(self.lbl_discord_username)
        dc_names.addWidget(self.lbl_discord_handle)
        dc_top.addLayout(dc_names, 1)

        self.btn_discord_toggle = QPushButton("AN")
        self.btn_discord_toggle.setObjectName("btn_discord_toggle")
        self.btn_discord_toggle.setFixedSize(34, 22)
        self.btn_discord_toggle.setToolTip("Rich Presence aktivieren / stummschalten")
        self.btn_discord_toggle.clicked.connect(self.toggle_discord_rpc)
        dc_top.addWidget(self.btn_discord_toggle)

        dc_layout.addLayout(dc_top)

        self.lbl_discord_status = QLabel("DISCORD: BEREIT")
        self.lbl_discord_status.setObjectName("discord_status_indicator")
        self.lbl_discord_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #8e99ac; letter-spacing: 0.5px;")
        dc_layout.addWidget(self.lbl_discord_status)

        self.btn_discord_auth = QPushButton("MIT DISCORD ANMELDEN")
        self.btn_discord_auth.setObjectName("btn_account_action")
        self.btn_discord_auth.clicked.connect(self.handle_discord_auth_click)
        dc_layout.addWidget(self.btn_discord_auth)

        sb_layout.addWidget(self.discord_card)

        sb_layout.addSpacing(14)

        # Navigation
        lbl_nav = QLabel("M E D I A T H E K")
        lbl_nav.setObjectName("section_eyebrow")
        sb_layout.addWidget(lbl_nav)

        self.btn_nav_home = QPushButton("  Home")
        self.btn_nav_home.setIcon(IconFactory.home("#38bdf8", 18))
        self.btn_nav_home.setIconSize(QSize(18, 18))
        self.btn_nav_home.setObjectName("nav_button")
        self.btn_nav_home.clicked.connect(lambda: self.switch_view(PAGE_HOME))
        sb_layout.addWidget(self.btn_nav_home)

        self.btn_nav_search = QPushButton("  Suche & Entdecken")
        self.btn_nav_search.setIcon(IconFactory.search("#8e99ac", 18))
        self.btn_nav_search.setIconSize(QSize(18, 18))
        self.btn_nav_search.setObjectName("nav_button")
        self.btn_nav_search.clicked.connect(lambda: self.switch_view(PAGE_SEARCH))
        sb_layout.addWidget(self.btn_nav_search)

        self.btn_nav_playlists = QPushButton("  Meine Playlists")
        self.btn_nav_playlists.setIcon(IconFactory.playlist("#8e99ac", 18))
        self.btn_nav_playlists.setIconSize(QSize(18, 18))
        self.btn_nav_playlists.setObjectName("nav_button")
        self.btn_nav_playlists.clicked.connect(self.open_playlists_view)
        sb_layout.addWidget(self.btn_nav_playlists)

        self.btn_nav_albums = QPushButton("  Meine Alben")
        self.btn_nav_albums.setIcon(IconFactory.disc("#8e99ac", 18))
        self.btn_nav_albums.setIconSize(QSize(18, 18))
        self.btn_nav_albums.setObjectName("nav_button")
        self.btn_nav_albums.clicked.connect(self.open_albums_view)
        sb_layout.addWidget(self.btn_nav_albums)

        self.btn_nav_liked = QPushButton("  Lieblingslieder")
        self.btn_nav_liked.setIcon(IconFactory.heart(filled=True, color="#38bdf8", size=18))
        self.btn_nav_liked.setIconSize(QSize(18, 18))
        self.btn_nav_liked.setObjectName("nav_button")
        self.btn_nav_liked.clicked.connect(self.open_liked_songs_view)
        sb_layout.addWidget(self.btn_nav_liked)

        sb_layout.addSpacing(14)

        lbl_local = QLabel("L O K A L")
        lbl_local.setObjectName("section_eyebrow")
        sb_layout.addWidget(lbl_local)

        self.btn_nav_queue = QPushButton(f"  Warteschlange ({len(self.queue)})")
        self.btn_nav_queue.setIcon(IconFactory.queue("#8e99ac", 18))
        self.btn_nav_queue.setIconSize(QSize(18, 18))
        self.btn_nav_queue.setObjectName("nav_button")
        self.btn_nav_queue.clicked.connect(lambda: self.switch_view(PAGE_QUEUE))
        sb_layout.addWidget(self.btn_nav_queue)

        self.btn_nav_favs = QPushButton(f"  Favoriten ({len(self.favorites)})")
        self.btn_nav_favs.setIcon(IconFactory.heart(filled=False, color="#8e99ac", size=18))
        self.btn_nav_favs.setIconSize(QSize(18, 18))
        self.btn_nav_favs.setObjectName("nav_button")
        self.btn_nav_favs.clicked.connect(lambda: self.switch_view(PAGE_FAVORITES))
        sb_layout.addWidget(self.btn_nav_favs)

        self.btn_nav_hist = QPushButton("  Verlauf")
        self.btn_nav_hist.setIcon(IconFactory.history("#8e99ac", 18))
        self.btn_nav_hist.setIconSize(QSize(18, 18))
        self.btn_nav_hist.setObjectName("nav_button")
        self.btn_nav_hist.clicked.connect(lambda: self.switch_view(PAGE_HISTORY))
        sb_layout.addWidget(self.btn_nav_hist)

        self.nav_buttons = {
            PAGE_HOME: self.btn_nav_home,
            PAGE_SEARCH: self.btn_nav_search,
            PAGE_PLAYLISTS: self.btn_nav_playlists,
            PAGE_ALBUMS: self.btn_nav_albums,
            PAGE_LIKED: self.btn_nav_liked,
            PAGE_QUEUE: self.btn_nav_queue,
            PAGE_FAVORITES: self.btn_nav_favs,
            PAGE_HISTORY: self.btn_nav_hist,
        }

        sb_layout.addStretch()

        lbl_quick = QLabel("E N T D E C K E N")
        lbl_quick.setObjectName("section_eyebrow")
        sb_layout.addWidget(lbl_quick)

        genres = [
            ("Charts", "Top Charts 2026"),
            ("Lofi Beats", "Lofi Hip Hop chill beats"),
            ("Rock Classics", "Rock Classics"),
            ("Synthwave", "Synthwave Retrowave"),
            ("Gaming EDM", "Gaming Music EDM")
        ]
        for name, query in genres:
            chip = QPushButton(name)
            chip.setObjectName("btn_genre")
            chip.clicked.connect(lambda checked, q=query: self.trigger_quick_search(q))
            sb_layout.addWidget(chip)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebar_scroll")
        sidebar_scroll.setFixedWidth(240)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sidebar_scroll.setWidget(sidebar)

        split_layout.addWidget(sidebar_scroll)

        # =====================================================================
        # 2. Main Content Stack
        # =====================================================================
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("content_area")

        # Page 0: HOME-Bildschirm (Statischer robuster Aufbau)
        self.setup_home_view()
        self.content_stack.addWidget(self.view_home)

        # Page 1: Suche & Entdecken
        view_search = QWidget()
        vs_layout = QVBoxLayout(view_search)
        vs_layout.setContentsMargins(32, 24, 32, 20)
        vs_layout.setSpacing(16)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Titel, Interpret, Album oder YouTube-URL suchen...")
        self.search_input.setObjectName("search_input")
        self.search_input.returnPressed.connect(self.start_search)
        search_bar.addWidget(self.search_input)

        btn_search = QPushButton("Suchen")
        btn_search.setObjectName("btn_primary")
        btn_search.setFixedWidth(90)
        btn_search.clicked.connect(self.start_search)
        search_bar.addWidget(btn_search)
        vs_layout.addLayout(search_bar)

        s_header = QHBoxLayout()
        self.lbl_search_header = QLabel("SUCHERGEBNISSE")
        self.lbl_search_header.setObjectName("section_title")
        s_header.addWidget(self.lbl_search_header)
        s_header.addStretch()

        btn_play_all = QPushButton("Alle abspielen")
        btn_play_all.setObjectName("btn_secondary")
        btn_play_all.clicked.connect(self.play_all_search_results)
        s_header.addWidget(btn_play_all)
        vs_layout.addLayout(s_header)

        self.list_search = QListWidget()
        self.list_search.setObjectName("track_list")
        self.list_search.itemDoubleClicked.connect(self.on_search_item_double_clicked)
        vs_layout.addWidget(self.list_search)
        self.content_stack.addWidget(view_search)

        # Page 2: Google Playlists Übersicht
        view_playlists = QWidget()
        vp_layout = QVBoxLayout(view_playlists)
        vp_layout.setContentsMargins(32, 24, 32, 20)
        vp_layout.setSpacing(16)

        p_header = QHBoxLayout()
        self.lbl_playlists_title = QLabel("MEINE GOOGLE PLAYLISTS")
        self.lbl_playlists_title.setObjectName("section_title")
        p_header.addWidget(self.lbl_playlists_title)
        p_header.addStretch()

        btn_refresh_p = QPushButton("Aktualisieren")
        btn_refresh_p.setObjectName("btn_secondary")
        btn_refresh_p.clicked.connect(self.open_playlists_view)
        p_header.addWidget(btn_refresh_p)
        vp_layout.addLayout(p_header)

        self.list_playlists = QListWidget()
        self.list_playlists.setObjectName("track_list")
        self.list_playlists.itemClicked.connect(self.on_playlist_item_clicked)
        vp_layout.addWidget(self.list_playlists)
        self.content_stack.addWidget(view_playlists)

        # Page 3: Playlist Detail
        view_pdetail = QWidget()
        vpd_layout = QVBoxLayout(view_pdetail)
        vpd_layout.setContentsMargins(32, 24, 32, 20)
        vpd_layout.setSpacing(16)

        pd_header = QHBoxLayout()
        btn_back_p = QPushButton(" Zurück")
        btn_back_p.setObjectName("btn_secondary")
        btn_back_p.setIcon(IconFactory.arrow_left("#94a3b8", 16))
        btn_back_p.setIconSize(QSize(14, 14))
        btn_back_p.clicked.connect(lambda: self.switch_view(PAGE_PLAYLISTS))
        pd_header.addWidget(btn_back_p)

        self.lbl_pdetail_title = QLabel("PLAYLIST INHALT")
        self.lbl_pdetail_title.setObjectName("section_title")
        pd_header.addWidget(self.lbl_pdetail_title)
        pd_header.addStretch()

        btn_play_all_p = QPushButton("Alle abspielen")
        btn_play_all_p.setObjectName("btn_primary")
        btn_play_all_p.clicked.connect(self.play_all_playlist_tracks)
        pd_header.addWidget(btn_play_all_p)
        vpd_layout.addLayout(pd_header)

        self.list_pdetail = QListWidget()
        self.list_pdetail.setObjectName("track_list")
        self.list_pdetail.itemDoubleClicked.connect(self.on_pdetail_item_double_clicked)
        vpd_layout.addWidget(self.list_pdetail)
        self.content_stack.addWidget(view_pdetail)

        # Page 4: Google Alben Übersicht
        view_albums = QWidget()
        va_layout = QVBoxLayout(view_albums)
        va_layout.setContentsMargins(32, 24, 32, 20)
        va_layout.setSpacing(16)

        a_header = QHBoxLayout()
        self.lbl_albums_title = QLabel("MEINE GOOGLE ALBEN")
        self.lbl_albums_title.setObjectName("section_title")
        a_header.addWidget(self.lbl_albums_title)
        a_header.addStretch()

        btn_refresh_a = QPushButton("Aktualisieren")
        btn_refresh_a.setObjectName("btn_secondary")
        btn_refresh_a.clicked.connect(self.open_albums_view)
        a_header.addWidget(btn_refresh_a)
        va_layout.addLayout(a_header)

        self.list_albums = QListWidget()
        self.list_albums.setObjectName("track_list")
        self.list_albums.itemClicked.connect(self.on_album_item_clicked)
        va_layout.addWidget(self.list_albums)
        self.content_stack.addWidget(view_albums)

        # Page 5: Album Detail
        view_adetail = QWidget()
        vad_layout = QVBoxLayout(view_adetail)
        vad_layout.setContentsMargins(32, 24, 32, 20)
        vad_layout.setSpacing(16)

        ad_header = QHBoxLayout()
        btn_back_a = QPushButton(" Zurück")
        btn_back_a.setObjectName("btn_secondary")
        btn_back_a.setIcon(IconFactory.arrow_left("#94a3b8", 16))
        btn_back_a.setIconSize(QSize(14, 14))
        btn_back_a.clicked.connect(lambda: self.switch_view(PAGE_ALBUMS))
        ad_header.addWidget(btn_back_a)

        self.lbl_adetail_title = QLabel("ALBUM TITEL")
        self.lbl_adetail_title.setObjectName("section_title")
        ad_header.addWidget(self.lbl_adetail_title)
        ad_header.addStretch()

        btn_play_all_a = QPushButton("Alle abspielen")
        btn_play_all_a.setObjectName("btn_primary")
        btn_play_all_a.clicked.connect(self.play_all_album_tracks)
        ad_header.addWidget(btn_play_all_a)
        vad_layout.addLayout(ad_header)

        self.list_adetail = QListWidget()
        self.list_adetail.setObjectName("track_list")
        self.list_adetail.itemDoubleClicked.connect(self.on_adetail_item_double_clicked)
        vad_layout.addWidget(self.list_adetail)
        self.content_stack.addWidget(view_adetail)

        # Page 6: Lieblingslieder
        view_liked = QWidget()
        vl_layout = QVBoxLayout(view_liked)
        vl_layout.setContentsMargins(32, 24, 32, 20)
        vl_layout.setSpacing(16)

        l_header = QHBoxLayout()
        self.lbl_liked_title = QLabel("LIEBLINGSLIEDER")
        self.lbl_liked_title.setObjectName("section_title")
        l_header.addWidget(self.lbl_liked_title)
        l_header.addStretch()

        btn_play_all_l = QPushButton("Alle abspielen")
        btn_play_all_l.setObjectName("btn_primary")
        btn_play_all_l.clicked.connect(self.play_all_liked_tracks)
        l_header.addWidget(btn_play_all_l)
        vl_layout.addLayout(l_header)

        self.list_liked = QListWidget()
        self.list_liked.setObjectName("track_list")
        self.list_liked.itemDoubleClicked.connect(self.on_liked_item_double_clicked)
        vl_layout.addWidget(self.list_liked)
        self.content_stack.addWidget(view_liked)

        # Page 7: Warteschlange
        view_queue = QWidget()
        vq_layout = QVBoxLayout(view_queue)
        vq_layout.setContentsMargins(32, 24, 32, 20)
        vq_layout.setSpacing(16)

        q_header = QHBoxLayout()
        self.lbl_queue_title = QLabel("WARTESCHLANGE")
        self.lbl_queue_title.setObjectName("section_title")
        q_header.addWidget(self.lbl_queue_title)
        q_header.addStretch()

        btn_clear_q = QPushButton("Leeren")
        btn_clear_q.setObjectName("btn_secondary")
        btn_clear_q.clicked.connect(self.clear_queue)
        q_header.addWidget(btn_clear_q)
        vq_layout.addLayout(q_header)

        self.list_queue = QListWidget()
        self.list_queue.setObjectName("track_list")
        self.list_queue.itemDoubleClicked.connect(self.on_queue_item_double_clicked)
        vq_layout.addWidget(self.list_queue)
        self.content_stack.addWidget(view_queue)

        # Page 8: Lokale Favoriten
        view_favs = QWidget()
        vf_layout = QVBoxLayout(view_favs)
        vf_layout.setContentsMargins(32, 24, 32, 20)
        vf_layout.setSpacing(16)

        f_header = QHBoxLayout()
        self.lbl_favs_title = QLabel("LOKALE FAVORITEN")
        self.lbl_favs_title.setObjectName("section_title")
        f_header.addWidget(self.lbl_favs_title)
        f_header.addStretch()

        btn_play_all_f = QPushButton("Alle abspielen")
        btn_play_all_f.setObjectName("btn_primary")
        btn_play_all_f.clicked.connect(self.play_all_favorites)
        f_header.addWidget(btn_play_all_f)
        vf_layout.addLayout(f_header)

        self.list_favs = QListWidget()
        self.list_favs.setObjectName("track_list")
        self.list_favs.itemDoubleClicked.connect(self.on_fav_item_double_clicked)
        vf_layout.addWidget(self.list_favs)
        self.content_stack.addWidget(view_favs)

        # Page 9: Verlauf
        view_hist = QWidget()
        vh_layout = QVBoxLayout(view_hist)
        vh_layout.setContentsMargins(32, 24, 32, 20)
        vh_layout.setSpacing(16)

        h_header = QHBoxLayout()
        lbl_h_title = QLabel("WIEDERGABEVERLAUF")
        lbl_h_title.setObjectName("section_title")
        h_header.addWidget(lbl_h_title)
        h_header.addStretch()

        btn_clear_h = QPushButton("Leeren")
        btn_clear_h.setObjectName("btn_secondary")
        btn_clear_h.clicked.connect(self.clear_history)
        h_header.addWidget(btn_clear_h)
        vh_layout.addLayout(h_header)

        self.list_hist = QListWidget()
        self.list_hist.setObjectName("track_list")
        self.list_hist.itemDoubleClicked.connect(self.on_hist_item_double_clicked)
        vh_layout.addWidget(self.list_hist)
        self.content_stack.addWidget(view_hist)

        # Page 10: Discord Login View
        self.setup_discord_login_view()
        self.content_stack.addWidget(self.view_discord_login)

        split_layout.addWidget(self.content_stack, 1)
        main_layout.addLayout(split_layout, 1)

        # =====================================================================
        # 3. Bottom Player Bar
        # =====================================================================
        player_bar = QFrame()
        player_bar.setObjectName("player_bar")
        player_bar.setFixedHeight(94)
        pb_layout = QHBoxLayout(player_bar)
        pb_layout.setContentsMargins(24, 12, 24, 12)
        pb_layout.setSpacing(20)

        left_box = QHBoxLayout()
        left_box.setSpacing(14)

        self.current_thumb = QLabel()
        self.current_thumb.setFixedSize(58, 58)
        self.current_thumb.setStyleSheet("background-color: #141720; border: 1px solid #232733; border-radius: 6px;")
        self.current_thumb.setScaledContents(True)
        left_box.addWidget(self.current_thumb)

        meta_box = QVBoxLayout()
        meta_box.setSpacing(3)
        meta_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.current_title_lbl = QLabel("Kein Titel ausgewählt")
        self.current_title_lbl.setStyleSheet("font-weight: 700; font-size: 14px; color: #f8fafc;")
        self.current_title_lbl.setFixedWidth(230)
        self.current_title_lbl.setWordWrap(False)

        self.current_artist_lbl = QLabel("Bereit zum Abspielen")
        self.current_artist_lbl.setStyleSheet("font-size: 12px; color: #8e99ac;")
        self.current_artist_lbl.setFixedWidth(230)

        meta_box.addWidget(self.current_title_lbl)
        meta_box.addWidget(self.current_artist_lbl)
        left_box.addLayout(meta_box)

        self.btn_fav_current = QPushButton()
        self.btn_fav_current.setObjectName("btn_ctrl_round")
        self.btn_fav_current.setFixedSize(36, 36)
        self.btn_fav_current.setIcon(IconFactory.heart(filled=False, color="#8e99ac", size=18))
        self.btn_fav_current.setIconSize(QSize(18, 18))
        self.btn_fav_current.setToolTip("Zu Favoriten hinzufügen (F)")
        self.btn_fav_current.clicked.connect(self.toggle_current_favorite)
        left_box.addWidget(self.btn_fav_current)

        pb_layout.addLayout(left_box)

        center_box = QVBoxLayout()
        center_box.setSpacing(6)
        center_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(14)
        ctrl_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_shuffle = QPushButton()
        self.btn_shuffle.setObjectName("btn_ctrl_round")
        self.btn_shuffle.setFixedSize(36, 36)
        self.btn_shuffle.setIcon(IconFactory.shuffle("#8e99ac", 18))
        self.btn_shuffle.setIconSize(QSize(18, 18))
        self.btn_shuffle.setToolTip("Zufallswiedergabe")
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        ctrl_row.addWidget(self.btn_shuffle)

        self.btn_prev = QPushButton()
        self.btn_prev.setObjectName("btn_ctrl_round")
        self.btn_prev.setFixedSize(38, 38)
        self.btn_prev.setIcon(IconFactory.prev("#cbd5e1", 20))
        self.btn_prev.setIconSize(QSize(18, 18))
        self.btn_prev.setToolTip("Vorheriger Titel (P)")
        self.btn_prev.clicked.connect(self.play_prev)
        ctrl_row.addWidget(self.btn_prev)

        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setObjectName("btn_play_main")
        self.btn_play_pause.setFixedSize(50, 50)
        self.btn_play_pause.setIcon(IconFactory.play("#090a0f", 22))
        self.btn_play_pause.setIconSize(QSize(20, 20))
        self.btn_play_pause.setToolTip("Wiedergabe / Pause (Leertaste)")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        ctrl_row.addWidget(self.btn_play_pause)

        self.btn_next = QPushButton()
        self.btn_next.setObjectName("btn_ctrl_round")
        self.btn_next.setFixedSize(38, 38)
        self.btn_next.setIcon(IconFactory.next("#cbd5e1", 20))
        self.btn_next.setIconSize(QSize(18, 18))
        self.btn_next.setToolTip("Nächster Titel (N)")
        self.btn_next.clicked.connect(self.play_next)
        ctrl_row.addWidget(self.btn_next)

        self.btn_repeat = QPushButton()
        self.btn_repeat.setObjectName("btn_ctrl_round")
        self.btn_repeat.setFixedSize(36, 36)
        self.btn_repeat.setIcon(IconFactory.repeat("#8e99ac", 18, one=False))
        self.btn_repeat.setIconSize(QSize(18, 18))
        self.btn_repeat.setToolTip("Wiederholungsmodus")
        self.btn_repeat.clicked.connect(self.toggle_repeat)
        ctrl_row.addWidget(self.btn_repeat)

        center_box.addLayout(ctrl_row)

        time_row = QHBoxLayout()
        time_row.setSpacing(10)

        self.lbl_elapsed = QLabel("0:00")
        self.lbl_elapsed.setStyleSheet("font-size: 11px; color: #64748b; font-family: monospace;")
        time_row.addWidget(self.lbl_elapsed)

        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setObjectName("progress_slider")
        self.slider_progress.setRange(0, 1000)
        self.slider_progress.sliderMoved.connect(self.on_seek_moved)
        self.slider_progress.sliderReleased.connect(self.on_seek_released)
        time_row.addWidget(self.slider_progress)

        self.lbl_total = QLabel("0:00")
        self.lbl_total.setStyleSheet("font-size: 11px; color: #64748b; font-family: monospace;")
        time_row.addWidget(self.lbl_total)

        center_box.addLayout(time_row)
        pb_layout.addLayout(center_box, 1)

        right_box = QHBoxLayout()
        right_box.setSpacing(12)

        self.lbl_stream_status = QLabel("BEREIT")
        self.lbl_stream_status.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 700; letter-spacing: 0.5px;")
        right_box.addWidget(self.lbl_stream_status)

        self.btn_mute = QPushButton()
        self.btn_mute.setObjectName("btn_ctrl_round")
        self.btn_mute.setFixedSize(36, 36)
        self.btn_mute.setIcon(IconFactory.volume(muted=False, color="#8e99ac", size=18))
        self.btn_mute.setIconSize(QSize(18, 18))
        self.btn_mute.setToolTip("Stummschalten (M)")
        self.btn_mute.clicked.connect(self.toggle_mute)
        right_box.addWidget(self.btn_mute)

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setObjectName("vol_slider")
        self.slider_vol.setFixedWidth(86)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(80)
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        right_box.addWidget(self.slider_vol)

        pb_layout.addLayout(right_box)
        main_layout.addWidget(player_bar)

    # -------------------------------------------------------------------------
    # Home-Bildschirm (Stabiler Aufbau & Live-Aktualisierung)
    # -------------------------------------------------------------------------
    def setup_home_view(self):
        self.view_home = QScrollArea()
        self.view_home.setObjectName("home_scroll")
        self.view_home.setWidgetResizable(True)
        self.view_home.setFrameShape(QFrame.Shape.NoFrame)

        home_container = QWidget()
        home_container.setObjectName("home_container")
        self.home_layout = QVBoxLayout(home_container)
        self.home_layout.setContentsMargins(36, 28, 36, 28)
        self.home_layout.setSpacing(22)

        # 1. Begrüßungs-Header
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        self.lbl_home_greeting = QLabel("Guten Tag")
        self.lbl_home_greeting.setStyleSheet("font-size: 26px; font-weight: 800; color: #f8fafc; letter-spacing: -0.5px;")
        self.lbl_home_sub = QLabel("Bereit für deine Musik")
        self.lbl_home_sub.setStyleSheet("font-size: 13px; color: #7e8b9f;")
        header_box.addWidget(self.lbl_home_greeting)
        header_box.addWidget(self.lbl_home_sub)
        self.home_layout.addLayout(header_box)

        # 2. Schnellzugriff-Karten (3 Spalten x 2 Zeilen)
        lbl_sec_quick = QLabel("SCHNELLZUGRIFF")
        lbl_sec_quick.setObjectName("section_eyebrow")
        self.home_layout.addWidget(lbl_sec_quick)

        grid_cards = QGridLayout()
        grid_cards.setSpacing(12)

        c_liked, self.lbl_card_liked_sub = self.create_quick_card(
            IconFactory.heart, filled=True, icon_color="#38bdf8",
            title="Lieblingslieder",
            desc="Aus YouTube Music",
            on_click=self.open_liked_songs_view
        )
        grid_cards.addWidget(c_liked, 0, 0)

        c_pl, self.lbl_card_playlists_sub = self.create_quick_card(
            IconFactory.playlist, filled=False, icon_color="#38bdf8",
            title="Meine Playlists",
            desc="Persönliche Listen",
            on_click=self.open_playlists_view
        )
        grid_cards.addWidget(c_pl, 0, 1)

        c_alb, self.lbl_card_albums_sub = self.create_quick_card(
            IconFactory.disc, filled=False, icon_color="#38bdf8",
            title="Meine Alben",
            desc="Gespeicherte Alben",
            on_click=self.open_albums_view
        )
        grid_cards.addWidget(c_alb, 0, 2)

        c_queue, self.lbl_card_queue_sub = self.create_quick_card(
            IconFactory.queue, filled=False, icon_color="#38bdf8",
            title="Warteschlange",
            desc=f"{len(self.queue)} Titel",
            on_click=lambda: self.switch_view(PAGE_QUEUE)
        )
        grid_cards.addWidget(c_queue, 1, 0)

        c_favs, self.lbl_card_favs_sub = self.create_quick_card(
            IconFactory.heart, filled=False, icon_color="#38bdf8",
            title="Lokale Favoriten",
            desc=f"{len(self.favorites)} Favoriten",
            on_click=lambda: self.switch_view(PAGE_FAVORITES)
        )
        grid_cards.addWidget(c_favs, 1, 1)

        c_search, _ = self.create_quick_card(
            IconFactory.search, filled=False, icon_color="#38bdf8",
            title="Suche & Entdecken",
            desc="Musik, Alben & mehr",
            on_click=lambda: self.switch_view(PAGE_SEARCH)
        )
        grid_cards.addWidget(c_search, 1, 2)

        self.home_layout.addLayout(grid_cards)

        # 3. Zuletzt gehört (Verlauf)
        lbl_sec_recent = QLabel("ZULETZT GEHÖRT")
        lbl_sec_recent.setObjectName("section_eyebrow")
        self.home_layout.addWidget(lbl_sec_recent)

        self.lbl_home_empty_recent = QLabel("Noch keine Titel im Verlauf. Nutze die Suche oder wähle eine Playlist.")
        self.lbl_home_empty_recent.setStyleSheet("color: #64748b; font-size: 12px; padding: 12px 4px;")
        self.home_layout.addWidget(self.lbl_home_empty_recent)

        self.list_home_recent = QListWidget()
        self.list_home_recent.setObjectName("track_list")
        self.list_home_recent.itemDoubleClicked.connect(self.on_home_recent_item_double_clicked)
        self.home_layout.addWidget(self.list_home_recent)

        # 4. Stimmungen & Mixe (3 Spalten x 2 Zeilen)
        lbl_sec_mixes = QLabel("STIMMUNGEN & MIXE")
        lbl_sec_mixes.setObjectName("section_eyebrow")
        self.home_layout.addWidget(lbl_sec_mixes)

        mix_grid = QGridLayout()
        mix_grid.setSpacing(12)

        mixes = [
            ("Lofi Chillout", "Entspannte Beats zum Konzentrieren", "Lofi Hip Hop chill beats"),
            ("Rock Classics", "Die größten Rock-Hymnen", "Rock Classics"),
            ("Synthwave & Retro", "Elektronische 80s Klangwelten", "Synthwave Retrowave"),
            ("Gaming High Energy", "Schneller Bass und EDM", "Gaming Music EDM"),
            ("Acoustic Sessions", "Ruhige akustische Titel", "Acoustic Chill Hits"),
            ("Top Charts", "Aktuelle weltweite Hits", "Top Charts 2026")
        ]

        for i, (m_title, m_desc, m_query) in enumerate(mixes):
            card = self.create_mix_card(m_title, m_desc, m_query)
            mix_grid.addWidget(card, i // 3, i % 3)

        self.home_layout.addLayout(mix_grid)
        self.home_layout.addStretch()

        self.view_home.setWidget(home_container)

    def create_quick_card(self, icon_func, filled=False, icon_color="#38bdf8", title="", desc="", on_click=None):
        card = ClickableCard()
        card.setFixedHeight(68)
        card_l = QHBoxLayout(card)
        card_l.setContentsMargins(14, 12, 14, 12)
        card_l.setSpacing(12)

        icon_box = QLabel()
        if icon_func == IconFactory.heart:
            pix = icon_func(filled=filled, color=icon_color, size=20).pixmap(20, 20)
        else:
            pix = icon_func(color=icon_color, size=20).pixmap(20, 20)
        icon_box.setPixmap(pix)
        icon_box.setFixedSize(36, 36)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet("background-color: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px;")
        icon_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card_l.addWidget(icon_box)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")
        t_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(t_lbl)

        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet("font-size: 11px; color: #7e8b9f;")
        d_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(d_lbl)

        card_l.addLayout(text_layout, 1)

        if on_click:
            card.clicked.connect(on_click)

        return card, d_lbl

    def create_mix_card(self, title, desc, query):
        card = ClickableCard()
        card.setFixedHeight(64)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 10, 14, 10)
        card_l.setSpacing(3)
        card_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")
        t_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card_l.addWidget(t_lbl)

        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet("font-size: 11px; color: #7e8b9f;")
        d_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card_l.addWidget(d_lbl)

        card.clicked.connect(lambda: self.trigger_quick_search(query))
        return card

    def refresh_home_view(self):
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            greeting = "Guten Morgen"
        elif 12 <= hour < 18:
            greeting = "Guten Tag"
        else:
            greeting = "Guten Abend"
        self.lbl_home_greeting.setText(greeting)

        if hasattr(self, "lbl_card_queue_sub"):
            self.lbl_card_queue_sub.setText(f"{len(self.queue)} Titel")
        if hasattr(self, "lbl_card_favs_sub"):
            self.lbl_card_favs_sub.setText(f"{len(self.favorites)} Favoriten")

        self.refresh_home_recent()

    def refresh_home_recent(self):
        recent_tracks = self.history[:5]
        if recent_tracks:
            self.lbl_home_empty_recent.hide()
            self.list_home_recent.show()
            self.list_home_recent.setFixedHeight(min(300, len(recent_tracks) * 58))
            self.populate_list(self.list_home_recent, recent_tracks, is_queue=False)
        else:
            self.list_home_recent.clear()
            self.list_home_recent.hide()
            self.lbl_home_empty_recent.show()

    def on_home_recent_item_double_clicked(self, item):
        widget = self.list_home_recent.itemWidget(item)
        if widget and hasattr(widget, "track"):
            self.play_track_now(widget.track)

    # -------------------------------------------------------------------------
    # Discord Login Bildschirm (Exklusiver Anmelde-View)
    # -------------------------------------------------------------------------
    def setup_discord_login_view(self):
        self.view_discord_login = QWidget()
        vdl_outer = QVBoxLayout(self.view_discord_login)
        vdl_outer.setContentsMargins(40, 40, 40, 40)
        vdl_outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("discord_login_card")
        card.setFixedWidth(540)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(36, 32, 36, 32)
        card_l.setSpacing(16)
        card_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Discord Logo
        icon_lbl = QLabel()
        icon_lbl.setPixmap(IconFactory.discord(color="#5865f2", size=56).pixmap(56, 56))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_l.addWidget(icon_lbl)

        # Title & Subtitle
        lbl_title = QLabel("YPlayer Discord-Anmeldung")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #f8fafc; letter-spacing: 0.5px;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_l.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Melde dich mit deinem Discord-Account an, um YPlayer mit synchronisierter "
            "Rich-Presence-Anzeige und YouTube-Track-Verknüpfung zu nutzen."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 12px; color: #94a3b8; line-height: 1.4;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_l.addWidget(lbl_desc)

        card_l.addSpacing(4)

        # Features
        feats_box = QVBoxLayout()
        feats_box.setSpacing(8)

        feats = [
            "Echtzeit-Anzeige deines aktuellen Musiktitels & Interpreten in Discord",
            "Direkter 'Auf YouTube anhören'-Button in deinem Profil",
            "Profil-Avatar & Nutzername-Synchronisation im Player",
            "Native Kopplung ohne externe Webseiten oder Passwörter"
        ]
        for f in feats:
            row = QHBoxLayout()
            row.setSpacing(10)
            c_icon = QLabel()
            c_icon.setPixmap(IconFactory.check("#38bdf8", 16).pixmap(16, 16))
            c_icon.setFixedSize(16, 16)
            row.addWidget(c_icon)
            f_lbl = QLabel(f)
            f_lbl.setStyleSheet("font-size: 12px; color: #cbd5e1;")
            row.addWidget(f_lbl)
            row.addStretch()
            feats_box.addLayout(row)

        card_l.addLayout(feats_box)
        card_l.addSpacing(6)

        # Status Label
        self.lbl_login_status = QLabel("Bereit zur Anmeldung")
        self.lbl_login_status.setObjectName("login_status_lbl")
        self.lbl_login_status.setStyleSheet("font-size: 11px; color: #8e99ac; font-weight: 600;")
        self.lbl_login_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_l.addWidget(self.lbl_login_status)

        # Primary Button: Mit Discord anmelden
        self.btn_login_discord = QPushButton("  Mit Discord anmelden")
        self.btn_login_discord.setObjectName("btn_discord_login_primary")
        self.btn_login_discord.setIcon(IconFactory.discord(color="#ffffff", size=18))
        self.btn_login_discord.setIconSize(QSize(18, 18))
        self.btn_login_discord.setFixedHeight(44)
        self.btn_login_discord.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login_discord.clicked.connect(self.start_discord_login)
        card_l.addWidget(self.btn_login_discord)

        # Secondary Button: Gast / Später
        self.btn_login_skip = QPushButton("Ohne Discord fortfahren (Gast-Modus)")
        self.btn_login_skip.setObjectName("btn_login_skip")
        self.btn_login_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login_skip.clicked.connect(self.skip_discord_login)
        card_l.addWidget(self.btn_login_skip)

        vdl_outer.addWidget(card)

    # -------------------------------------------------------------------------
    # Styling: Schlicht, Dunkel, Hochwertig
    # -------------------------------------------------------------------------
    def apply_theme(self):
        qss = """
        QMainWindow {
            background-color: #090a0f;
            color: #f1f5f9;
        }
        #sidebar_scroll {
            background-color: #0e1017;
            border-right: 1px solid #1a1d26;
        }
        #sidebar {
            background-color: #0e1017;
            border: none;
        }
        #brand_label {
            font-size: 16px;
            font-weight: 800;
            color: #f8fafc;
            letter-spacing: 2px;
        }
        #account_card {
            background-color: #131620;
            border: 1px solid #202432;
            border-radius: 6px;
        }
        #status_indicator {
            font-size: 10px;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: 0.5px;
        }
        #btn_account_action {
            background-color: #1a1e2b;
            border: 1px solid #282e40;
            border-radius: 4px;
            color: #cbd5e1;
            font-size: 11px;
            font-weight: 600;
            padding: 5px 8px;
        }
        #btn_account_action:hover {
            background-color: #242a3c;
            border-color: #38bdf8;
            color: #ffffff;
        }
        #discord_card {
            background-color: #131620;
            border: 1px solid #202432;
            border-radius: 6px;
        }
        #btn_discord_toggle {
            background-color: #1a1e2b;
            border: 1px solid #282e40;
            border-radius: 4px;
            color: #5865f2;
            font-size: 10px;
            font-weight: 700;
        }
        #btn_discord_toggle:hover {
            background-color: #242a3c;
            border-color: #5865f2;
            color: #ffffff;
        }
        #discord_login_card {
            background-color: #11141f;
            border: 1px solid #23293a;
            border-radius: 12px;
        }
        #btn_discord_login_primary {
            background-color: #5865f2;
            color: #ffffff;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            border: none;
            padding: 8px 16px;
        }
        #btn_discord_login_primary:hover {
            background-color: #4752c4;
        }
        #btn_discord_login_primary:pressed {
            background-color: #3c45a5;
        }
        #btn_login_skip {
            background: transparent;
            color: #64748b;
            border: none;
            font-size: 11px;
            padding: 4px;
        }
        #btn_login_skip:hover {
            color: #94a3b8;
            text-decoration: underline;
        }
        #section_eyebrow {
            font-size: 10px;
            font-weight: 700;
            color: #555e6d;
            letter-spacing: 1.5px;
            padding-left: 2px;
        }
        #nav_button {
            text-align: left;
            padding: 9px 12px;
            border-radius: 6px;
            background: transparent;
            color: #94a3b8;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid transparent;
        }
        #nav_button:hover {
            background-color: #151822;
            color: #f8fafc;
            border-color: #222634;
        }
        #btn_genre {
            text-align: left;
            padding: 6px 12px;
            border-radius: 4px;
            background-color: #131620;
            color: #717d91;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid #1b1e2a;
        }
        #btn_genre:hover {
            background-color: #1b1f2d;
            color: #e2e8f0;
            border-color: #2b3142;
        }
        #content_area {
            background-color: #090a0f;
        }
        #home_scroll {
            background-color: #090a0f;
            border: none;
        }
        #home_container {
            background-color: #090a0f;
        }
        #home_card {
            background-color: #12151e;
            border: 1px solid #1e222e;
            border-radius: 8px;
        }
        #home_card:hover {
            background-color: #181c28;
            border-color: #38bdf8;
        }
        QScrollBar:vertical {
            background: #090a0f;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #1c202d;
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #2a3144;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        #section_title {
            font-size: 17px;
            font-weight: 800;
            color: #f8fafc;
            letter-spacing: 0.5px;
        }
        #search_input {
            background-color: #12151e;
            border: 1px solid #202432;
            border-radius: 6px;
            padding: 10px 16px;
            color: #f8fafc;
            font-size: 13px;
        }
        #search_input:focus {
            border: 1px solid #38bdf8;
            background-color: #151824;
        }
        #btn_primary {
            background-color: #f8fafc;
            color: #090a0f;
            border-radius: 6px;
            font-weight: 700;
            font-size: 12px;
            padding: 8px 16px;
            border: none;
        }
        #btn_primary:hover {
            background-color: #38bdf8;
        }
        #btn_secondary {
            background-color: #131620;
            color: #94a3b8;
            border: 1px solid #202432;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            padding: 7px 14px;
        }
        #btn_secondary:hover {
            background-color: #1b1f2d;
            color: #f8fafc;
            border-color: #38bdf8;
        }
        #track_list {
            background-color: transparent;
            border: none;
            outline: none;
        }
        #track_list::item {
            background-color: #11141b;
            border: 1px solid #1a1e28;
            border-radius: 6px;
            margin-bottom: 5px;
            padding: 2px;
        }
        #track_list::item:hover {
            background-color: #161a25;
            border-color: #252a3a;
        }
        #track_list::item:selected {
            background-color: #172030;
            border-color: #38bdf8;
        }
        #btn_row_play {
            background-color: #1c212e;
            border: 1px solid #2a3144;
            border-radius: 16px;
        }
        #btn_row_play:hover {
            background-color: #38bdf8;
            border-color: #38bdf8;
        }
        #btn_row_icon {
            background-color: #141720;
            border: 1px solid #202534;
            border-radius: 16px;
        }
        #btn_row_icon:hover {
            background-color: #202535;
            border-color: #38bdf8;
        }
        #player_bar {
            background-color: #0e1017;
            border-top: 1px solid #1a1d26;
        }
        #btn_play_main {
            background-color: #f8fafc;
            border-radius: 25px;
            border: none;
        }
        #btn_play_main:hover {
            background-color: #38bdf8;
        }
        #btn_ctrl_round {
            background-color: #131620;
            border: 1px solid #202432;
            border-radius: 18px;
        }
        #btn_ctrl_round:hover {
            background-color: #1d212f;
            border-color: #38bdf8;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #202432;
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: #38bdf8;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #f8fafc;
            width: 12px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 3px;
        }
        """
        self.setStyleSheet(qss)

    # -------------------------------------------------------------------------
    # Shortcuts
    # -------------------------------------------------------------------------
    def setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.seek_relative(5000))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.seek_relative(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_N), self, self.play_next)
        QShortcut(QKeySequence(Qt.Key.Key_P), self, self.play_prev)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, self.toggle_mute)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.toggle_current_favorite)

    # -------------------------------------------------------------------------
    # Google Account Handhabung
    # -------------------------------------------------------------------------
    def update_google_status_ui(self):
        if self.yt_instance:
            self.lbl_google_status.setText("● GOOGLE VERBUNDEN")
            self.lbl_google_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
            self.btn_google_auth.setText("Abmelden")
            self.btn_nav_playlists.setEnabled(True)
            self.btn_nav_albums.setEnabled(True)
            self.btn_nav_liked.setEnabled(True)
        else:
            self.lbl_google_status.setText("○ NICHT ANGEMELDET")
            self.lbl_google_status.setStyleSheet("color: #64748b; font-weight: bold;")
            self.btn_google_auth.setText("Mit Google anmelden")

    def handle_google_auth(self):
        if self.yt_instance:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink(missing_ok=True)
            self.yt_instance = None
            self.update_google_status_ui()
            QMessageBox.information(self, "Abgemeldet", "Google-Konto wurde getrennt.")
            self.switch_view(PAGE_HOME)
            return

        self.lbl_google_status.setText("● VERBINDE...")
        self.google_worker = GoogleLoginWorker()
        self.google_worker.finished.connect(self.on_google_login_finished)
        self.google_worker.start()

    def on_google_login_finished(self, success, message):
        if success:
            self.yt_instance = build_ytmusic_from_saved()
            self.update_google_status_ui()
            QMessageBox.information(self, "Erfolg", "Erfolgreich mit deinem Google-Konto verbunden!\nDeine Playlists und Alben sind jetzt verfügbar.")
            self.refresh_home_view()
        else:
            self.update_google_status_ui()
            QMessageBox.warning(self, "Anmeldung", f"Konnte nicht anmelden: {message}\n\nTipp: Stelle sicher, dass du in Firefox auf youtube.com angemeldet bist.")

    # -------------------------------------------------------------------------
    # Discord Authentifizierung & RPC Handhabung
    # -------------------------------------------------------------------------
    def get_discord_avatar_pixmap(self, user_data, size=32):
        if not user_data:
            return None
        av_path = user_data.get("avatar_path")
        if av_path and os.path.exists(av_path):
            try:
                pix = QPixmap(av_path)
                if not pix.isNull():
                    return make_circular_pixmap(pix, size)
            except Exception:
                pass

        uid = user_data.get("id")
        if uid:
            cached = CACHE_THUMBS / f"discord_avatar_{uid}.png"
            if cached.exists():
                try:
                    pix = QPixmap(str(cached))
                    if not pix.isNull():
                        return make_circular_pixmap(pix, size)
                except Exception:
                    pass

        return None

    def on_discord_user_authenticated(self, user):
        if not user or not user.get("id"):
            return
        uid = user.get("id")
        av = user.get("avatar")
        av_path = download_discord_avatar(uid, av)
        if av_path:
            user["avatar_path"] = av_path
        user["logged_in_at"] = int(time.time())
        save_discord_session(user)
        self.discord_user = user
        self.update_discord_account_ui()

    def update_discord_account_ui(self):
        if not hasattr(self, "discord_card"):
            return

        enabled = self.settings.get("discord_rpc", True)
        connected = self.discord_worker.is_connected if hasattr(self, "discord_worker") else False

        # Status & Toggle-Button
        if enabled:
            self.btn_discord_toggle.setText("AN")
            self.btn_discord_toggle.setStyleSheet("color: #5865f2; border-color: #5865f2; background-color: rgba(88, 101, 242, 0.12);")
        else:
            self.btn_discord_toggle.setText("AUS")
            self.btn_discord_toggle.setStyleSheet("color: #64748b; border-color: #202432;")

        if self.discord_user:
            # Benutzer ist bei Discord angemeldet
            global_name = self.discord_user.get("global_name") or self.discord_user.get("username", "Discord User")
            username = self.discord_user.get("username", "")

            self.lbl_discord_username.setText(global_name[:16])
            self.lbl_discord_handle.setText(f"@{username}"[:18] if username else "")

            pix = self.get_discord_avatar_pixmap(self.discord_user, size=32)
            if pix:
                self.discord_avatar_lbl.setPixmap(pix)
            else:
                self.discord_avatar_lbl.setPixmap(IconFactory.discord(color="#5865f2", size=20).pixmap(20, 20))

            if not enabled:
                self.lbl_discord_status.setText("DISCORD: STUMM")
                self.lbl_discord_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
            elif connected:
                self.lbl_discord_status.setText("● DISCORD VERBUNDEN")
                self.lbl_discord_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #5865f2; letter-spacing: 0.5px;")
            else:
                self.lbl_discord_status.setText("DISCORD: BEREIT")
                self.lbl_discord_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #8e99ac; letter-spacing: 0.5px;")

            self.btn_discord_auth.setText("ABMELDEN")
            self.btn_discord_auth.setStyleSheet("background-color: #1a1e2b; border: 1px solid #282e40; color: #f43f5e; font-size: 10px; font-weight: 700; padding: 4px;")
        else:
            # Nicht angemeldet
            self.lbl_discord_username.setText("DISCORD KONTO")
            self.lbl_discord_handle.setText("Nicht angemeldet")
            self.discord_avatar_lbl.setPixmap(IconFactory.discord(color="#64748b", size=20).pixmap(20, 20))
            self.lbl_discord_status.setText("DISCORD: GETRENNT")
            self.lbl_discord_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
            self.btn_discord_auth.setText("MIT DISCORD ANMELDEN")
            self.btn_discord_auth.setStyleSheet("background-color: #5865f2; border: none; color: #ffffff; font-size: 10px; font-weight: 700; padding: 5px; border-radius: 4px;")

    def on_discord_connection_changed(self, connected):
        self.update_discord_account_ui()
        if connected:
            self.update_discord_status(self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def toggle_discord_rpc(self):
        new_state = not self.settings.get("discord_rpc", True)
        self.settings["discord_rpc"] = new_state
        save_json(SETTINGS_FILE, self.settings)
        self.discord_worker.set_enabled(new_state)
        self.update_discord_account_ui()
        if new_state:
            self.update_discord_status(self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def handle_discord_auth_click(self):
        if self.discord_user:
            reply = QMessageBox.question(
                self,
                "Discord-Konto abmelden",
                "Möchtest du dein Discord-Konto wirklich abmelden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.logout_discord()
        else:
            self.switch_view(PAGE_DISCORD_LOGIN)
            self.start_discord_login()

    def start_discord_login(self):
        if hasattr(self, "discord_login_worker") and self.discord_login_worker and self.discord_login_worker.isRunning():
            return

        self.btn_login_discord.setEnabled(False)
        self.lbl_login_status.setText("Verbindungsaufbau zu Discord...")
        self.lbl_login_status.setStyleSheet("font-size: 11px; color: #38bdf8; font-weight: 700;")

        self.discord_login_worker = DiscordLoginWorker()
        self.discord_login_worker.status_updated.connect(self.on_discord_login_status)
        self.discord_login_worker.finished.connect(self.on_discord_login_finished)
        self.discord_login_worker.start()

    def on_discord_login_status(self, text):
        if hasattr(self, "lbl_login_status"):
            self.lbl_login_status.setText(text)

    def on_discord_login_finished(self, success, user, message):
        self.btn_login_discord.setEnabled(True)
        if success:
            self.discord_user = user
            self.discord_worker.set_enabled(True)
            self.update_discord_account_ui()
            self.lbl_login_status.setText(message)
            self.lbl_login_status.setStyleSheet("font-size: 11px; color: #10b981; font-weight: 700;")
            self.switch_view(PAGE_HOME)
            self.update_discord_status(self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        else:
            self.lbl_login_status.setText(message)
            self.lbl_login_status.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 600;")

    def skip_discord_login(self):
        self.switch_view(PAGE_HOME)

    def logout_discord(self):
        clear_discord_session()
        self.discord_user = None
        if hasattr(self, "discord_worker"):
            self.discord_worker.clear_track()
            self.discord_worker.set_enabled(False)
        self.update_discord_account_ui()
        self.switch_view(PAGE_DISCORD_LOGIN)

    def update_discord_status(self, is_playing=True):
        if not hasattr(self, "discord_worker") or not self.settings.get("discord_rpc", True):
            return
        if self.current_index >= 0 and self.current_index < len(self.queue):
            track = self.queue[self.current_index]
            pos_ms = self.player.position()
            dur_ms = self.player.duration()
            self.discord_worker.update_track(track, is_playing=is_playing, position_ms=pos_ms, duration_ms=dur_ms)
        else:
            self.discord_worker.clear_track()

    # -------------------------------------------------------------------------
    # Navigation & Views
    # -------------------------------------------------------------------------
    def switch_view(self, index):
        self.content_stack.setCurrentIndex(index)
        self.update_nav_active(index)
        if index == PAGE_HOME:
            self.refresh_home_view()
        elif index == PAGE_QUEUE:
            self.refresh_queue_view()
        elif index == PAGE_FAVORITES:
            self.refresh_favs_view()
        elif index == PAGE_HISTORY:
            self.refresh_hist_view()

    def update_nav_active(self, current_page):
        if not hasattr(self, "nav_buttons"):
            return
        for page, btn in self.nav_buttons.items():
            if page == current_page:
                btn.setStyleSheet("background-color: #171b26; color: #f8fafc; border-color: #2b3345; font-weight: 700;")
            else:
                btn.setStyleSheet("")

    def update_badge_counts(self):
        self.btn_nav_queue.setText(f"  Warteschlange ({len(self.queue)})")
        self.btn_nav_favs.setText(f"  Favoriten ({len(self.favorites)})")
        if hasattr(self, "lbl_card_queue_sub"):
            self.lbl_card_queue_sub.setText(f"{len(self.queue)} Titel")
        if hasattr(self, "lbl_card_favs_sub"):
            self.lbl_card_favs_sub.setText(f"{len(self.favorites)} Favoriten")

    # -------------------------------------------------------------------------
    # Google Playlists View
    # -------------------------------------------------------------------------
    def open_playlists_view(self):
        if not self.yt_instance:
            self.handle_google_auth()
            return

        self.switch_view(PAGE_PLAYLISTS)
        self.list_playlists.clear()
        self.lbl_playlists_title.setText("LADE PLAYLISTS...")

        self.playlists_worker = PlaylistsWorker(self.yt_instance)
        self.playlists_worker.finished.connect(self.on_playlists_loaded)
        self.playlists_worker.error.connect(lambda e: self.lbl_playlists_title.setText(f"Fehler: {e}"))
        self.playlists_worker.start()

    def on_playlists_loaded(self, playlists):
        self.playlists_data = playlists
        self.lbl_playlists_title.setText(f"MEINE GOOGLE PLAYLISTS ({len(playlists)})")
        self.list_playlists.clear()

        for p in playlists:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 56))

            thumb_url = ""
            if p.get("thumbnails"):
                thumb_url = p["thumbnails"][-1].get("url", "")

            track_repr = {
                "id": p.get("playlistId"),
                "title": p.get("title", "Unbenannte Playlist"),
                "uploader": f"{p.get('count', '')} Titel",
                "duration": "PLAYLIST",
                "thumbnail": thumb_url
            }

            row = TrackRowWidget(track_repr, is_queue=False)
            row.play_btn.setToolTip("Playlist öffnen")
            row.play_btn.clicked.disconnect()
            row.play_btn.clicked.connect(lambda checked, pl=p: self.open_playlist_detail(pl))
            row.queue_btn.hide()
            row.fav_btn.hide()

            self.request_thumbnail(track_repr, row)
            self.list_playlists.addItem(item)
            self.list_playlists.setItemWidget(item, row)

    def on_playlist_item_clicked(self, item):
        row = self.list_playlists.row(item)
        if hasattr(self, "playlists_data") and 0 <= row < len(self.playlists_data):
            self.open_playlist_detail(self.playlists_data[row])

    def open_playlist_detail(self, playlist):
        self.switch_view(PAGE_PLAYLIST_DETAIL)
        pid = playlist.get("playlistId")
        title = playlist.get("title", "Playlist")
        self.lbl_pdetail_title.setText(f"{title.upper()} (LADE TITEL...)")
        self.list_pdetail.clear()

        self.pdetail_worker = PlaylistTracksWorker(self.yt_instance, pid)
        self.pdetail_worker.finished.connect(self.on_playlist_detail_loaded)
        self.pdetail_worker.error.connect(lambda e: self.lbl_pdetail_title.setText(f"Fehler: {e}"))
        self.pdetail_worker.start()

    def on_playlist_detail_loaded(self, data):
        title = data.get("title", "Playlist")
        raw_tracks = data.get("tracks", [])
        self.current_playlist_tracks = []

        for t in raw_tracks:
            if not t or not t.get("videoId"):
                continue
            dur = t.get("duration") or "--:--"
            artists = ", ".join([a.get("name", "") for a in t.get("artists", [])]) or "Unbekannt"
            thumb = ""
            if t.get("thumbnails"):
                thumb = t["thumbnails"][-1].get("url", "")

            self.current_playlist_tracks.append({
                "id": t.get("videoId"),
                "title": t.get("title", "Unbekannter Titel"),
                "uploader": artists,
                "duration": dur,
                "thumbnail": thumb or f"https://i.ytimg.com/vi/{t.get('videoId')}/hqdefault.jpg"
            })

        self.lbl_pdetail_title.setText(f"{title.upper()} ({len(self.current_playlist_tracks)} TITEL)")
        self.populate_list(self.list_pdetail, self.current_playlist_tracks, is_queue=False)

    def play_all_playlist_tracks(self):
        if hasattr(self, "current_playlist_tracks") and self.current_playlist_tracks:
            self.queue = list(self.current_playlist_tracks)
            self.update_badge_counts()
            self.play_index(0)

    def on_pdetail_item_double_clicked(self, item):
        widget = self.list_pdetail.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    # -------------------------------------------------------------------------
    # Google Alben View
    # -------------------------------------------------------------------------
    def open_albums_view(self):
        if not self.yt_instance:
            self.handle_google_auth()
            return

        self.switch_view(PAGE_ALBUMS)
        self.list_albums.clear()
        self.lbl_albums_title.setText("LADE ALBEN...")

        self.albums_worker = AlbumsWorker(self.yt_instance)
        self.albums_worker.finished.connect(self.on_albums_loaded)
        self.albums_worker.error.connect(lambda e: self.lbl_albums_title.setText(f"Fehler: {e}"))
        self.albums_worker.start()

    def on_albums_loaded(self, albums):
        self.albums_data = albums
        self.lbl_albums_title.setText(f"MEINE GOOGLE ALBEN ({len(albums)})")
        self.list_albums.clear()

        for a in albums:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 56))

            thumb_url = ""
            if a.get("thumbnails"):
                thumb_url = a["thumbnails"][-1].get("url", "")
            artists = ", ".join([art.get("name", "") for art in a.get("artists", [])]) or a.get("year", "")

            track_repr = {
                "id": a.get("browseId"),
                "title": a.get("title", "Unbekanntes Album"),
                "uploader": artists,
                "duration": "ALBUM",
                "thumbnail": thumb_url
            }

            row = TrackRowWidget(track_repr, is_queue=False)
            row.play_btn.setToolTip("Album öffnen")
            row.play_btn.clicked.disconnect()
            row.play_btn.clicked.connect(lambda checked, alb=a: self.open_album_detail(alb))
            row.queue_btn.hide()
            row.fav_btn.hide()

            self.request_thumbnail(track_repr, row)
            self.list_albums.addItem(item)
            self.list_albums.setItemWidget(item, row)

    def on_album_item_clicked(self, item):
        row = self.list_albums.row(item)
        if hasattr(self, "albums_data") and 0 <= row < len(self.albums_data):
            self.open_album_detail(self.albums_data[row])

    def open_album_detail(self, album):
        self.switch_view(PAGE_ALBUM_DETAIL)
        bid = album.get("browseId")
        title = album.get("title", "Album")
        self.lbl_adetail_title.setText(f"{title.upper()} (LADE TITEL...)")
        self.list_adetail.clear()

        self.adetail_worker = AlbumTracksWorker(self.yt_instance, bid)
        self.adetail_worker.finished.connect(self.on_album_detail_loaded)
        self.adetail_worker.error.connect(lambda e: self.lbl_adetail_title.setText(f"Fehler: {e}"))
        self.adetail_worker.start()

    def on_album_detail_loaded(self, data):
        title = data.get("title", "Album")
        artist = ", ".join([a.get("name", "") for a in data.get("artists", [])]) or ""
        raw_tracks = data.get("tracks", [])
        self.current_album_tracks = []

        for t in raw_tracks:
            if not t or not t.get("videoId"):
                continue
            dur = t.get("duration") or "--:--"
            t_artist = ", ".join([a.get("name", "") for a in t.get("artists", [])]) or artist
            thumb = ""
            if t.get("thumbnails"):
                thumb = t["thumbnails"][-1].get("url", "")

            self.current_album_tracks.append({
                "id": t.get("videoId"),
                "title": t.get("title", "Unbekannter Titel"),
                "uploader": t_artist,
                "duration": dur,
                "thumbnail": thumb or f"https://i.ytimg.com/vi/{t.get('videoId')}/hqdefault.jpg"
            })

        self.lbl_adetail_title.setText(f"{title.upper()} - {artist} ({len(self.current_album_tracks)} TITEL)")
        self.populate_list(self.list_adetail, self.current_album_tracks, is_queue=False)

    def play_all_album_tracks(self):
        if hasattr(self, "current_album_tracks") and self.current_album_tracks:
            self.queue = list(self.current_album_tracks)
            self.update_badge_counts()
            self.play_index(0)

    def on_adetail_item_double_clicked(self, item):
        widget = self.list_adetail.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    # -------------------------------------------------------------------------
    # Lieblingslieder View
    # -------------------------------------------------------------------------
    def open_liked_songs_view(self):
        if not self.yt_instance:
            self.handle_google_auth()
            return

        self.switch_view(PAGE_LIKED)
        self.list_liked.clear()
        self.lbl_liked_title.setText("LADE LIEBLINGSLIEDER...")

        self.liked_worker = LikedSongsWorker(self.yt_instance)
        self.liked_worker.finished.connect(self.on_liked_songs_loaded)
        self.liked_worker.error.connect(lambda e: self.lbl_liked_title.setText(f"Fehler: {e}"))
        self.liked_worker.start()

    def on_liked_songs_loaded(self, tracks):
        self.current_liked_tracks = []
        for t in tracks:
            if not t or not t.get("videoId"):
                continue
            dur = t.get("duration") or "--:--"
            artists = ", ".join([a.get("name", "") for a in t.get("artists", [])]) or "Unbekannt"
            thumb = ""
            if t.get("thumbnails"):
                thumb = t["thumbnails"][-1].get("url", "")

            self.current_liked_tracks.append({
                "id": t.get("videoId"),
                "title": t.get("title", "Unbekannter Titel"),
                "uploader": artists,
                "duration": dur,
                "thumbnail": thumb or f"https://i.ytimg.com/vi/{t.get('videoId')}/hqdefault.jpg"
            })

        self.lbl_liked_title.setText(f"LIEBLINGSLIEDER ({len(self.current_liked_tracks)} TITEL)")
        self.populate_list(self.list_liked, self.current_liked_tracks, is_queue=False)

    def play_all_liked_tracks(self):
        if hasattr(self, "current_liked_tracks") and self.current_liked_tracks:
            self.queue = list(self.current_liked_tracks)
            self.update_badge_counts()
            self.play_index(0)

    def on_liked_item_double_clicked(self, item):
        widget = self.list_liked.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    # -------------------------------------------------------------------------
    # Suche & Thumbnails
    # -------------------------------------------------------------------------
    def trigger_quick_search(self, q):
        self.search_input.setText(q)
        self.switch_view(PAGE_SEARCH)
        self.start_search()

    def start_search(self):
        q = self.search_input.text().strip()
        if not q:
            return

        self.switch_view(PAGE_SEARCH)
        self.lbl_search_header.setText(f"SUCHE NACH '{q.upper()}'...")
        self.list_search.clear()

        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()

        self.search_worker = SearchWorker(q)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.error.connect(lambda err: self.lbl_search_header.setText(f"FEHLER: {err}"))
        self.search_worker.start()

    def on_search_finished(self, results):
        self.search_results = results
        self.lbl_search_header.setText(f"SUCHERGEBNISSE ({len(results)})")
        self.populate_list(self.list_search, results, is_queue=False)

    def populate_list(self, list_widget, tracks, is_queue=False):
        list_widget.clear()
        for track in tracks:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 56))
            is_playing = (self.current_index >= 0 and self.current_index < len(self.queue) and self.queue[self.current_index]["id"] == track["id"])
            is_fav = any(f["id"] == track["id"] for f in self.favorites)

            row = TrackRowWidget(track, is_queue=is_queue, is_playing=is_playing, is_fav=is_fav)
            row.play_requested.connect(self.play_track_now)
            row.queue_requested.connect(self.add_to_queue)
            row.fav_requested.connect(self.toggle_favorite)
            row.remove_requested.connect(self.remove_from_queue)

            self.request_thumbnail(track, row)
            list_widget.addItem(item)
            list_widget.setItemWidget(item, row)

    def request_thumbnail(self, track, row_widget):
        t_id = track.get("id")
        if not t_id:
            return
        if t_id in self.cached_pixmaps:
            row_widget.set_thumbnail(self.cached_pixmaps[t_id])
            return

        def on_done(tid, bytes_data):
            self.thumb_loaded_signal.emit(tid, bytes_data)

        task = ThumbnailLoader(track.get("thumbnail"), t_id, on_done)
        self.thread_pool.start(task)

    def on_thumb_loaded(self, t_id, bytes_data):
        img = QImage()
        if img.loadFromData(bytes_data):
            pix = QPixmap.fromImage(img)
            self.cached_pixmaps[t_id] = pix
            lists = [self.list_search, self.list_pdetail, self.list_adetail, self.list_liked, self.list_queue, self.list_favs, self.list_hist]
            if hasattr(self, "list_home_recent"):
                lists.insert(0, self.list_home_recent)
            for list_w in lists:
                for i in range(list_w.count()):
                    item = list_w.item(i)
                    widget = list_w.itemWidget(item)
                    if widget and widget.track.get("id") == t_id:
                        widget.set_thumbnail(pix)

            if self.current_index >= 0 and self.current_index < len(self.queue):
                if self.queue[self.current_index].get("id") == t_id:
                    self.current_thumb.setPixmap(pix)

    # -------------------------------------------------------------------------
    # Playback & Audio-Streaming mit Caching
    # -------------------------------------------------------------------------
    def play_track_now(self, track):
        for i, t in enumerate(self.queue):
            if t["id"] == track["id"]:
                self.play_index(i)
                return

        insert_pos = self.current_index + 1 if self.current_index >= 0 else len(self.queue)
        self.queue.insert(insert_pos, track)
        self.update_badge_counts()
        self.play_index(insert_pos)

    def play_index(self, index):
        if index < 0 or index >= len(self.queue):
            return

        self.current_index = index
        track = self.queue[index]

        self.current_title_lbl.setText(track.get("title", ""))
        self.current_artist_lbl.setText(track.get("uploader", ""))
        self.lbl_stream_status.setText("LÄDT CACHE...")

        if track["id"] in self.cached_pixmaps:
            self.current_thumb.setPixmap(self.cached_pixmaps[track["id"]])

        is_fav = any(f["id"] == track["id"] for f in self.favorites)
        self.update_current_fav_ui(is_fav)

        self.add_to_history(track)

        cached_file = get_cached_audio_path(track["id"])
        if cached_file:
            self.on_audio_ready(track, cached_file)
            return

        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.terminate()

        self.download_worker = AudioDownloadWorker(track)
        self.download_worker.ready.connect(self.on_audio_ready)
        self.download_worker.error.connect(lambda err: self.lbl_stream_status.setText(f"FEHLER: {err}"))
        self.download_worker.start()

        self.refresh_queue_view()

    def on_audio_ready(self, track, local_audio_path):
        self.lbl_stream_status.setText("SPIELT")
        self.player.setSource(QUrl.fromLocalFile(local_audio_path))
        self.player.play()
        self.btn_play_pause.setIcon(IconFactory.pause("#090a0f", 22))

        self.prefetch_next_track()
        self.update_discord_status(is_playing=True)

    def prefetch_next_track(self):
        if self.current_index + 1 < len(self.queue):
            next_track = self.queue[self.current_index + 1]
            task = PrefetchWorker(next_track.get("id"))
            self.thread_pool.start(task)

    def toggle_play_pause(self):
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play_pause.setIcon(IconFactory.play("#090a0f", 22))
            self.lbl_stream_status.setText("PAUSIERT")
            self.update_discord_status(is_playing=False)
        else:
            if self.player.source().isEmpty() and len(self.queue) > 0:
                self.play_index(0)
            else:
                self.player.play()
                self.btn_play_pause.setIcon(IconFactory.pause("#090a0f", 22))
                self.lbl_stream_status.setText("SPIELT")
                self.update_discord_status(is_playing=True)

    def play_next(self):
        if not self.queue:
            return

        if self.is_shuffle:
            import random
            next_idx = random.randint(0, len(self.queue) - 1)
            self.play_index(next_idx)
            return

        if self.current_index + 1 < len(self.queue):
            self.play_index(self.current_index + 1)
        elif self.repeat_mode == "all":
            self.play_index(0)
        else:
            self.lbl_stream_status.setText("ENDE")

    def play_prev(self):
        if not self.queue:
            return

        if self.player.position() > 3000:
            self.player.setPosition(0)
            return

        if self.current_index - 1 >= 0:
            self.play_index(self.current_index - 1)
        else:
            self.play_index(len(self.queue) - 1)

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.player.duration() > 0 and self.player.position() >= self.player.duration() - 2500:
                if self.repeat_mode == "one":
                    self.player.setPosition(0)
                    self.player.play()
                else:
                    self.play_next()

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setIcon(IconFactory.pause("#090a0f", 22))
        else:
            self.btn_play_pause.setIcon(IconFactory.play("#090a0f", 22))

    # -------------------------------------------------------------------------
    # Progress & Volume
    # -------------------------------------------------------------------------
    def on_position_changed(self, pos_ms):
        if not self.is_seeking:
            dur_ms = self.player.duration()
            if dur_ms > 0:
                val = int((pos_ms / dur_ms) * 1000)
                self.slider_progress.setValue(val)
            self.lbl_elapsed.setText(format_duration(pos_ms / 1000.0))

    def on_duration_changed(self, dur_ms):
        self.lbl_total.setText(format_duration(dur_ms / 1000.0))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.update_discord_status(is_playing=True)

    def on_seek_moved(self, val):
        self.is_seeking = True
        dur_ms = self.player.duration()
        if dur_ms > 0:
            pos = int((val / 1000.0) * dur_ms)
            self.lbl_elapsed.setText(format_duration(pos / 1000.0))

    def on_seek_released(self):
        dur_ms = self.player.duration()
        if dur_ms > 0:
            target_ms = int((self.slider_progress.value() / 1000.0) * dur_ms)
            self.player.setPosition(target_ms)
        self.is_seeking = False
        is_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.update_discord_status(is_playing=is_playing)

    def seek_relative(self, delta_ms):
        new_pos = max(0, min(self.player.duration(), self.player.position() + delta_ms))
        self.player.setPosition(new_pos)

    def on_volume_changed(self, val):
        self.audio_output.setVolume(val / 100.0)
        self.btn_mute.setIcon(IconFactory.volume(muted=(val == 0), color="#8e99ac", size=18))

    def toggle_mute(self):
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        self.btn_mute.setIcon(IconFactory.volume(muted=(not is_muted), color="#8e99ac", size=18))

    # -------------------------------------------------------------------------
    # Shuffle & Repeat
    # -------------------------------------------------------------------------
    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        color = "#38bdf8" if self.is_shuffle else "#8e99ac"
        self.btn_shuffle.setIcon(IconFactory.shuffle(color, 18))
        self.btn_shuffle.setStyleSheet("border-color: #38bdf8; background-color: rgba(56, 189, 248, 0.12);" if self.is_shuffle else "")

    def toggle_repeat(self):
        if self.repeat_mode == "off":
            self.repeat_mode = "all"
            self.btn_repeat.setIcon(IconFactory.repeat("#38bdf8", 18, one=False))
            self.btn_repeat.setStyleSheet("border-color: #38bdf8; background-color: rgba(56, 189, 248, 0.12);")
            self.btn_repeat.setToolTip("Wiederholen: Alle")
        elif self.repeat_mode == "all":
            self.repeat_mode = "one"
            self.btn_repeat.setIcon(IconFactory.repeat("#38bdf8", 18, one=True))
            self.btn_repeat.setStyleSheet("border-color: #38bdf8; background-color: rgba(56, 189, 248, 0.12);")
            self.btn_repeat.setToolTip("Wiederholen: 1 Titel")
        else:
            self.repeat_mode = "off"
            self.btn_repeat.setIcon(IconFactory.repeat("#8e99ac", 18, one=False))
            self.btn_repeat.setStyleSheet("")
            self.btn_repeat.setToolTip("Wiederholen: Aus")

    # -------------------------------------------------------------------------
    # Favoriten & Verlauf
    # -------------------------------------------------------------------------
    def update_current_fav_ui(self, is_fav):
        if is_fav:
            self.btn_fav_current.setIcon(IconFactory.heart(filled=True, color="#38bdf8", size=18))
            self.btn_fav_current.setStyleSheet("border-color: #38bdf8; background-color: rgba(56, 189, 248, 0.12);")
        else:
            self.btn_fav_current.setIcon(IconFactory.heart(filled=False, color="#8e99ac", size=18))
            self.btn_fav_current.setStyleSheet("")

    def toggle_current_favorite(self):
        if self.current_index >= 0 and self.current_index < len(self.queue):
            self.toggle_favorite(self.queue[self.current_index])

    def toggle_favorite(self, track):
        existing = [f for f in self.favorites if f["id"] == track["id"]]
        if existing:
            self.favorites = [f for f in self.favorites if f["id"] != track["id"]]
        else:
            self.favorites.insert(0, track)
        save_json(FAVORITES_FILE, self.favorites)
        self.update_badge_counts()

        if self.current_index >= 0 and self.current_index < len(self.queue) and self.queue[self.current_index]["id"] == track["id"]:
            self.update_current_fav_ui(not bool(existing))

        curr = self.content_stack.currentIndex()
        if curr == PAGE_FAVORITES:
            self.refresh_favs_view()
        elif curr == PAGE_SEARCH:
            self.populate_list(self.list_search, getattr(self, "search_results", []), is_queue=False)
        elif curr == PAGE_HOME:
            self.refresh_home_recent()

    def add_to_history(self, track):
        self.history = [h for h in self.history if h["id"] != track["id"]]
        self.history.insert(0, track)
        self.history = self.history[:100]
        save_json(HISTORY_FILE, self.history)
        if self.content_stack.currentIndex() == PAGE_HOME:
            self.refresh_home_recent()

    # -------------------------------------------------------------------------
    # Queue Handhabung
    # -------------------------------------------------------------------------
    def add_to_queue(self, track):
        self.queue.append(track)
        self.update_badge_counts()
        if self.content_stack.currentIndex() == PAGE_QUEUE:
            self.refresh_queue_view()
        if self.current_index == -1:
            self.play_index(0)

    def remove_from_queue(self, track):
        idx = next((i for i, t in enumerate(self.queue) if t["id"] == track["id"]), -1)
        if idx != -1:
            self.queue.pop(idx)
            if self.current_index >= idx:
                self.current_index = max(0, self.current_index - 1)
            self.update_badge_counts()
            if self.content_stack.currentIndex() == PAGE_QUEUE:
                self.refresh_queue_view()

    def clear_queue(self):
        self.queue.clear()
        self.current_index = -1
        self.update_badge_counts()
        if self.content_stack.currentIndex() == PAGE_QUEUE:
            self.refresh_queue_view()
        if hasattr(self, "discord_worker"):
            self.discord_worker.clear_track()

    def play_all_search_results(self):
        if hasattr(self, "search_results") and self.search_results:
            self.queue = list(self.search_results)
            self.update_badge_counts()
            self.play_index(0)

    def play_all_favorites(self):
        if self.favorites:
            self.queue = list(self.favorites)
            self.update_badge_counts()
            self.play_index(0)

    def clear_history(self):
        self.history.clear()
        save_json(HISTORY_FILE, [])
        self.refresh_hist_view()
        self.refresh_home_recent()

    def refresh_queue_view(self):
        self.populate_list(self.list_queue, self.queue, is_queue=True)

    def refresh_favs_view(self):
        self.populate_list(self.list_favs, self.favorites, is_queue=False)

    def refresh_hist_view(self):
        self.populate_list(self.list_hist, self.history, is_queue=False)

    def on_search_item_double_clicked(self, item):
        widget = self.list_search.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    def on_queue_item_double_clicked(self, item):
        row = self.list_queue.row(item)
        if row >= 0:
            self.play_index(row)

    def on_fav_item_double_clicked(self, item):
        widget = self.list_favs.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    def on_hist_item_double_clicked(self, item):
        widget = self.list_hist.itemWidget(item)
        if widget:
            self.play_track_now(widget.track)

    def closeEvent(self, event):
        if hasattr(self, "discord_worker"):
            self.discord_worker.stop()
        event.accept()


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------
def main():
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
    elif sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YPlayer.Music.Player.1.0")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("YPlayer")

    # Set Window Icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for icon_name in ("yplayer.ico", "yplayer.png"):
        icon_path = os.path.join(base_dir, icon_name)
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    font = QFont("Plus Jakarta Sans", 10)
    app.setFont(font)

    window = YPlayerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
