#!/usr/bin/env python3
import os
import shutil
import sys
import json
import platform
import threading
import time
from asyncio import start_server

import skin
import requests
import uuid as py_uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                               QProgressBar, QComboBox, QStackedWidget, QButtonGroup,
                               QCheckBox, QSpinBox, QFileDialog, QGroupBox, QFormLayout,
                               QSlider, QScrollArea, QFrame, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap
from offline import OfflineAuthProvider
from launcher import GameLauncher


# Inline SVGs (unchanged – only what we need)
PLAY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#ffffff" d="M8 5v14l11-7z"/>
</svg>"""
ACCOUNT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#ffffff" d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
</svg>"""
LOGS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#ffffff" d="M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z"/>
</svg>"""
SETTINGS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#ffffff" d="M19.14 12.94c0-.34-.02-.66-.06-.98l2.1-1.64c.24-.19.3-.52.14-.8l-1.96-3.4c-.16-.28-.46-.38-.74-.28l-2.48.98c-.56-.36-1.18-.64-1.86-.82L14.2 3.3c-.06-.28-.3-.48-.6-.48h-3.2c-.3 0-.54.2-.6.48l-.44 2.62c-.68.18-1.3.46-1.86.82l-2.48-.98c-.28-.1-.58 0-.74.28l-1.96 3.4c-.16.28-.1.6.14.8l2.1 1.64c-.04.32-.06.64-.06.98s.02.66.06.98l-2.1 1.64c-.24.19-.3.52-.14.8l1.96 3.4c.16.28.46.38.74.28l2.48-.98c.56.36 1.18.64 1.86.82l.44 2.62c.06.28.3.48.6.48h3.2c.3 0 .54-.2.6-.48l.44-2.62c.68-.18 1.3-.46 1.86-.82l2.48.98c.28.1.58 0 .74-.28l1.96-3.4c.16-.28.1-.6-.14-.8l-2.1-1.64c.04-.32.06-.64.06-.98zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
</svg>"""
SKIN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff">
  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08s5.97 1.09 6 3.08c-1.29 1.94-3.5 3.22-6 3.22z"/>
</svg>"""


def create_svg_icon(svg_string):
    byte_array = QByteArray(svg_string.encode('utf-8'))
    pixmap = QPixmap()
    pixmap.loadFromData(byte_array, "SVG")
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Settings (added authlib_enabled key)
# ---------------------------------------------------------------------------
class Settings:
    def __init__(self, path: str = "settings.json"):
        self._path = Path(path)
        self._data = {
            "fullscreen": True,
            "width": 854,
            "height": 480,
            "java_path": "java",
            "ram_mb": 2048,
            "java_args": "",
            "authlib_injector_path": "authlib-injector.jar",
            "authlib_injector_url": "http://localhost:25585",
            "authlib_enabled": True,
        }
        self.load()

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except Exception:
                pass

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()


# ---------------------------------------------------------------------------
# Manifest fetcher (unchanged)
# ---------------------------------------------------------------------------
class ManifestFetcherThread(QThread):
    versions_signal = Signal(list)

    def __init__(self):
        super().__init__()
        self._http = requests.Session()

    def run(self):
        try:
            url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
            manifest = self._http.get(url, timeout=5).json()
            versions = [v['id'] for v in manifest['versions'] if v['type'] == 'release']
            self.versions_signal.emit(versions)
        except Exception:
            self.versions_signal.emit([])


# ---------------------------------------------------------------------------
# Downloader thread (unchanged)
# ---------------------------------------------------------------------------
class DownloaderThread(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()
    file_progress_signal = Signal(int)
    file_index_signal = Signal(int, int, str)
    overall_progress_signal = Signal(int)

    def __init__(self, version: str, game_dir: Path):
        super().__init__()
        self.version = version
        self.game_dir = game_dir
        self.os_name = self._get_os_name()
        self._current_file = 0
        self._total_files = 0
        self._completed_parallel = 0
        self._parallel_lock = Lock()
        self._http = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=2)
        self._http.mount('https://', adapter)
        self._http.mount('http://', adapter)
        self._http.headers.update({"User-Agent": "SonicLauncher/2.0"})
        self._manifest = None
        self.CHUNK_SIZE = 65536
        self.LIB_WORKERS = 8
        self.ASSET_WORKERS = 16

    def _get_os_name(self):
        s = platform.system().lower()
        if s == 'windows':
            return 'windows'
        if s == 'darwin':
            return 'osx'
        return 'linux'

    def _download_single(self, url, path, desc="", chunk_size=None):
        self._current_file += 1
        if not desc:
            desc = path.name
        self.file_index_signal.emit(self._current_file, self._total_files, desc)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            self.file_progress_signal.emit(100)
            return
        if desc:
            self.log_signal.emit(f"Downloading {desc}...")
        self.file_progress_signal.emit(0)
        chunk = chunk_size or self.CHUNK_SIZE
        try:
            r = self._http.get(url, stream=True, timeout=15)
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            down = 0
            last = 0
            with open(path, 'wb') as f:
                for b in r.iter_content(chunk_size=chunk):
                    if b:
                        f.write(b)
                        down += len(b)
                        if total > 0:
                            pct = int((down / total) * 100)
                            if pct != last:
                                self.file_progress_signal.emit(pct)
                                last = pct
        except Exception as e:
            self.log_signal.emit(f"[WARNING] Failed {desc}: {e}")
        self.file_progress_signal.emit(100)

    def _download_parallel_lib(self, url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            with self._parallel_lock:
                self._completed_parallel += 1
            return True
        try:
            r = self._http.get(url, stream=True, timeout=15)
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=self.CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            self.log_signal.emit(f"[WARNING] Library download failed: {path.name} – {e}")
            return False
        finally:
            with self._parallel_lock:
                self._completed_parallel += 1
                done = self._completed_parallel
            overall = int((self._current_file + done) / self._total_files * 100)
            self.overall_progress_signal.emit(overall)
            self.file_index_signal.emit(self._current_file + done, self._total_files, f"lib: {path.name}")
        return True

    def _download_parallel_asset(self, url, path, desc):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            with self._parallel_lock:
                self._completed_parallel += 1
            return True
        try:
            r = self._http.get(url, stream=True, timeout=15)
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=self.CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            self.log_signal.emit(f"[WARNING] Asset download failed: {desc} – {e}")
            return False
        finally:
            with self._parallel_lock:
                self._completed_parallel += 1
                done = self._completed_parallel
            overall = int((self._current_file + done) / self._total_files * 100)
            self.overall_progress_signal.emit(overall)
            self.file_index_signal.emit(self._current_file + done, self._total_files, f"asset: {desc}")
        return True

    def run(self):
        try:
            if self._manifest is None:
                self.log_signal.emit("[INFO] Fetching Mojang version manifest...")
                manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
                resp = self._http.get(manifest_url, timeout=10)
                resp.raise_for_status()
                self._manifest = resp.json()

            version_url = next((v['url'] for v in self._manifest['versions'] if v['id'] == self.version), None)
            if not version_url:
                self.log_signal.emit(f"[ERROR] Version {self.version} not found.")
                return

            self.log_signal.emit(f"[INFO] Fetching JSON for {self.version}...")
            version_data = self._http.get(version_url, timeout=10).json()
            ver_dir = self.game_dir / "versions" / self.version
            ver_dir.mkdir(parents=True, exist_ok=True)
            with open(ver_dir / f"{self.version}.json", 'w') as f:
                json.dump(version_data, f)

            asset_index_info = version_data.get('assetIndex', {})
            total_assets = 0
            assets_data = None
            if asset_index_info:
                self.log_signal.emit("[INFO] Fetching asset index (counting)...")
                index_id = asset_index_info['id']
                index_path = self.game_dir / "assets" / "indexes" / f"{index_id}.json"
                self._download_single(asset_index_info['url'], index_path, f"asset index {index_id}.json")
                with open(index_path, 'r') as f:
                    assets_data = json.load(f)
                total_assets = len(assets_data.get('objects', {}))
                self.log_signal.emit(f"[INFO] Asset index contains {total_assets} files.")

            libraries = version_data.get('libraries', [])
            lib_jobs = []
            for lib in libraries:
                if 'downloads' in lib and 'artifact' in lib['downloads']:
                    art = lib['downloads']['artifact']
                    lib_jobs.append((art['url'], self.game_dir / "libraries" / art['path']))
                if 'natives' in lib and self.os_name in lib['natives']:
                    classifier = lib['natives'][self.os_name].replace("${arch}", "64")
                    if 'downloads' in lib and 'classifiers' in lib['downloads'] and classifier in lib['downloads'][
                        'classifiers']:
                        nat = lib['downloads']['classifiers'][classifier]
                        lib_jobs.append((nat['url'], self.game_dir / "libraries" / nat['path']))

            self._total_files = 1 + 1 + len(lib_jobs) + 1 + total_assets
            self._current_file = 0

            self._current_file += 1
            self.file_index_signal.emit(self._current_file, self._total_files, f"version {self.version}.json")
            self.file_progress_signal.emit(100)

            client_url = version_data['downloads']['client']['url']
            self._download_single(client_url, ver_dir / f"{self.version}.jar", "client.jar")

            self.log_signal.emit(
                f"[INFO] Downloading {len(lib_jobs)} libraries concurrently ({self.LIB_WORKERS} workers)...")
            self._completed_parallel = 0
            with ThreadPoolExecutor(max_workers=self.LIB_WORKERS) as executor:
                futs = [executor.submit(self._download_parallel_lib, url, path) for url, path in lib_jobs]
                for f in as_completed(futs):
                    pass
            self._current_file += len(lib_jobs)
            self.overall_progress_signal.emit(int(self._current_file / self._total_files * 100))

            if asset_index_info and total_assets > 0:
                objects = list(assets_data.get('objects', {}).items())
                self.log_signal.emit(
                    f"[INFO] Downloading {total_assets} assets concurrently ({self.ASSET_WORKERS} workers)...")
                tasks = [(f"https://resources.download.minecraft.net/{h[:2]}/{h}",
                          self.game_dir / "assets" / "objects" / h[:2] / h, key)
                         for key, val in objects if (h := val['hash'])]
                self._completed_parallel = 0
                with ThreadPoolExecutor(max_workers=self.ASSET_WORKERS) as executor:
                    futs = [executor.submit(self._download_parallel_asset, url, path, desc) for url, path, desc in
                            tasks]
                    for f in as_completed(futs):
                        pass
                self.overall_progress_signal.emit(100)

            self.log_signal.emit(f"[SUCCESS] Download of {self.version} complete!")
            self.file_progress_signal.emit(0)
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Download failed: {str(e)}")
        finally:
            self.finished_signal.emit()


# ==========================================================================
# NEW: Authlib download thread with real progress
# ==========================================================================
class AuthlibDownloadThread(QThread):
    progress_signal = Signal(int)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, url: str, target_path: str):
        super().__init__()
        self.url = url
        self.target_path = target_path

    def run(self):
        try:
            from urllib.request import urlopen, Request
            req = Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as response:
                total = int(response.headers.get("content-length", 0))
                chunk_size = 65536
                downloaded = 0
                with open(self.target_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int((downloaded / total) * 100)
                            self.progress_signal.emit(pct)
                        else:
                            # indeterminate – just pulse 1-99
                            self.progress_signal.emit(50)
                self.progress_signal.emit(100)
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------
class MinecraftLauncherGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCL - A Minecraft Launcher")
        self.resize(950, 600)
        self.game_dir = Path("./.minecraft")
        self.settings = Settings()
        self.game_process = None
        self.skin_process = None  # will hold the skin.py subprocess
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-weight: bold; }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #3c3f41;
                border: 1px solid #1e1e1e;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #3C8527; }
            QComboBox::drop-down { border: 0px; }
            QComboBox QAbstractItemView {
                background-color: #3c3f41;
                color: #ffffff;
                selection-background-color: #3C8527;
            }
            QCheckBox {
                color: #ffffff;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #555;
                background-color: #3c3f41;
            }
            QCheckBox::indicator:checked {
                background-color: #3C8527;
                border-color: #3C8527;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QPushButton:disabled { background-color: #333333; color: #777777; }
            QPushButton.navButton {
                background-color: transparent;
                border-radius: 0px;
                border-left: 3px solid transparent;
                padding: 15px;
            }
            QPushButton.navButton:hover { background-color: #383838; }
            QPushButton.navButton:checked {
                background-color: #2b2b2b;
                border-left: 3px solid #3C8527;
            }
            QPushButton#launchButton {
                background-color: #3C8527;
                font-size: 20px;
                padding: 15px 30px;
                border-radius: 4px;
                border-bottom: 4px solid #235214;
            }
            QPushButton#launchButton:hover { background-color: #43932A; }
            QPushButton#launchButton:pressed {
                background-color: #235214;
                border-bottom: 0px;
                margin-top: 4px;
            }
            QPushButton#launchButton:disabled {
                background-color: #444444;
                border-bottom: 4px solid #222222;
                color: #888888;
            }
            QProgressBar {
                border: none;
                background-color: #1e1e1e;
                text-align: center;
                color: #ffffff;
                border-radius: 2px;
            }
            QProgressBar::chunk { background-color: #3C8527; }
            QProgressBar#currentFileBar::chunk { background-color: #4A90D9; }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #111111;
                color: #cccccc;
                font-family: 'Consolas', 'Monospace';
                font-size: 13px;
                border-radius: 4px;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 6px;
                margin-top: 20px;
                padding: 20px 15px 15px 15px;
                color: #ffffff;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
        """)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Navigation panel (no skin button)
        nav_widget = QWidget()
        nav_widget.setStyleSheet("background-color: #1e1e1e;")
        nav_widget.setFixedWidth(65)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 20, 0, 20)
        nav_layout.setSpacing(10)

        self.btn_nav_play = QPushButton()
        self.btn_nav_play.setIcon(create_svg_icon(PLAY_SVG))
        self.btn_nav_play.setIconSize(QSize(28, 28))
        self.btn_nav_play.setProperty("class", "navButton")
        self.btn_nav_play.setCheckable(True)

        self.btn_nav_account = QPushButton()
        self.btn_nav_account.setIcon(create_svg_icon(ACCOUNT_SVG))
        self.btn_nav_account.setIconSize(QSize(28, 28))
        self.btn_nav_account.setProperty("class", "navButton")
        self.btn_nav_account.setCheckable(True)

        self.btn_nav_skin = QPushButton()
        self.btn_nav_skin.setIcon(create_svg_icon(SKIN_SVG))
        self.btn_nav_skin.setIconSize(QSize(28, 28))
        self.btn_nav_skin.setProperty("class", "navButton")
        self.btn_nav_skin.setCheckable(True)

        self.btn_nav_logs = QPushButton()
        self.btn_nav_logs.setIcon(create_svg_icon(LOGS_SVG))
        self.btn_nav_logs.setIconSize(QSize(28, 28))
        self.btn_nav_logs.setProperty("class", "navButton")
        self.btn_nav_logs.setCheckable(True)

        self.btn_nav_settings = QPushButton()
        self.btn_nav_settings.setIcon(create_svg_icon(SETTINGS_SVG))
        self.btn_nav_settings.setIconSize(QSize(28, 28))
        self.btn_nav_settings.setProperty("class", "navButton")
        self.btn_nav_settings.setCheckable(True)

        nav_layout.addWidget(self.btn_nav_play)
        nav_layout.addWidget(self.btn_nav_account)
        nav_layout.addWidget(self.btn_nav_skin)  # <-- ADDED
        nav_layout.addWidget(self.btn_nav_logs)
        nav_layout.addWidget(self.btn_nav_settings)
        nav_layout.addStretch()

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.addButton(self.btn_nav_play, 0)
        self.nav_group.addButton(self.btn_nav_account, 1)
        self.nav_group.addButton(self.btn_nav_skin, 2)  # <-- index 2
        self.nav_group.addButton(self.btn_nav_logs, 3)
        self.nav_group.addButton(self.btn_nav_settings, 4)
        self.nav_group.buttonClicked.connect(self._nav_clicked)

        # Pages (no skin page)
        self.pages = QStackedWidget()
        self.page_play = QWidget()
        self.page_account = QWidget()
        self.page_skin = QWidget()  # <-- NEW
        self.page_logs = QWidget()
        self.page_settings = QWidget()
        self.pages.addWidget(self.page_play)     # 0
        self.pages.addWidget(self.page_account)  # 1
        self.pages.addWidget(self.page_skin)  # 2  <-- NEW
        self.pages.addWidget(self.page_logs)     # 3
        self.pages.addWidget(self.page_settings)  # 4

        main_layout.addWidget(nav_widget)
        main_layout.addWidget(self.pages)

        self.btn_nav_play.setChecked(True)
        self.pages.setCurrentIndex(0)

        self._setup_play_tab()
        self._setup_account_tab()
        self._setup_skin_tab()  # <-- NEW
        self._setup_logs_tab()
        self._setup_settings_tab()


        self.downloader_thread = None
        self.load_player_data()
        self.user_input.editingFinished.connect(self.save_player_data)
        self.uuid_input.editingFinished.connect(self.save_player_data)

        self.fetcher = ManifestFetcherThread()
        self.fetcher.versions_signal.connect(self.on_versions_fetched)
        self.fetcher.start()

    # ---- navigation -------------------------------------------------
    def _nav_clicked(self, button):
        idx = self.nav_group.id(button)
        self.pages.setCurrentIndex(idx)

    def _switch_to_tab(self, index):
        self.pages.setCurrentIndex(index)
        self.nav_group.button(index).setChecked(True)

    # ---- Play tab --------------------------------------------------
    def _setup_play_tab(self):
        layout = QVBoxLayout(self.page_play)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch()
        ver_layout = QVBoxLayout()
        ver_label = QLabel("Select Version:")
        ver_label.setStyleSheet("font-size: 16px; color: #aaaaaa; margin-bottom: 5px;")
        self.ver_combo = QComboBox()
        self.ver_combo.setEditable(False)
        self.ver_combo.setMinimumHeight(45)
        self.ver_combo.addItem("Loading versions...")
        ver_layout.addWidget(ver_label)
        ver_layout.addWidget(self.ver_combo)
        layout.addLayout(ver_layout)
        layout.addSpacing(30)
        action_layout = QHBoxLayout()
        self.btn_download = QPushButton("Download")
        self.btn_download.setMinimumHeight(55)
        self.btn_download.setFixedWidth(140)
        self.btn_download.clicked.connect(self.start_download)
        self.btn_launch = QPushButton("PLAY")
        self.btn_launch.setObjectName("launchButton")
        self.btn_launch.setMinimumHeight(55)
        self.btn_launch.clicked.connect(self.launch_game)
        action_layout.addWidget(self.btn_download)
        action_layout.addWidget(self.btn_launch)
        layout.addLayout(action_layout)
        layout.addStretch()
        self.file_progress_label = QLabel("")
        self.file_progress_label.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        layout.addWidget(self.file_progress_label)
        overall_label = QLabel("Overall Progress:")
        overall_label.setStyleSheet("color: #aaaaaa; font-size: 13px; margin-top: 10px;")
        layout.addWidget(overall_label)
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setFixedHeight(10)
        layout.addWidget(self.overall_progress_bar)
        current_file_label = QLabel("Current File:")
        current_file_label.setStyleSheet("color: #aaaaaa; font-size: 13px; margin-top: 5px;")
        layout.addWidget(current_file_label)
        self.current_file_progress_bar = QProgressBar()
        self.current_file_progress_bar.setObjectName("currentFileBar")
        self.current_file_progress_bar.setValue(0)
        self.current_file_progress_bar.setFixedHeight(10)
        layout.addWidget(self.current_file_progress_bar)
        self.ver_combo.currentTextChanged.connect(self.check_version_status)

    # ---- Account tab ------------------------------------------------
    def _setup_account_tab(self):
        layout = QVBoxLayout(self.page_account)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        title = QLabel("Account Configuration")
        title.setStyleSheet("font-size: 24px; color: #ffffff; margin-bottom: 20px;")
        layout.addWidget(title)
        warning_label = QLabel(
            "Warning:\n- Changing UUID may mess with your server data...\n- Changing UUID may also mess with skins...")
        warning_label.setStyleSheet(
            "background-color: #3a3a1a; border: 1px solid #ffaa00; border-radius: 6px; padding: 12px; color: #ffcc00; font-weight: bold; font-size: 13px;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        user_label = QLabel("Username:")
        self.user_input = QLineEdit("DevPlayer")
        self.user_input.setMinimumHeight(40)
        layout.addWidget(user_label)
        layout.addWidget(self.user_input)
        uuid_label = QLabel("Player UUID:")
        self.uuid_input = QLineEdit()
        self.uuid_input.setMinimumHeight(40)
        self.uuid_input.setPlaceholderText("Must be configured to play...")
        layout.addWidget(uuid_label)
        layout.addWidget(self.uuid_input)
        self.btn_generate_uuid = QPushButton("Generate Random UUID")
        self.btn_generate_uuid.setMinimumHeight(40)
        self.btn_generate_uuid.clicked.connect(self.generate_uuid)
        layout.addWidget(self.btn_generate_uuid)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Skin tab
    # ------------------------------------------------------------------
    def _setup_skin_tab(self):
        layout = QVBoxLayout(self.page_skin)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title = QLabel("Skin Manager")
        title.setStyleSheet("font-size: 24px; color: #ffffff; margin-bottom: 10px;")
        layout.addWidget(title)

        # -- UUID display --
        uuid_layout = QHBoxLayout()
        uuid_label = QLabel("Current player UUID:")
        uuid_label.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        self.skin_uuid_display = QLabel("(load player.json first)")
        self.skin_uuid_display.setStyleSheet("font-size: 14px; color: #ffffff; font-family: monospace;")
        uuid_layout.addWidget(uuid_label)
        uuid_layout.addWidget(self.skin_uuid_display)
        uuid_layout.addStretch()
        layout.addLayout(uuid_layout)

        # -- Skin status --
        status_layout = QHBoxLayout()
        status_label = QLabel("Status:")
        status_label.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        self.skin_status = QLabel("Not checked")
        self.skin_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.skin_status)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # -- Preview area --
        preview_group = QGroupBox("Current Skin Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.skin_preview = QLabel("No skin loaded")
        self.skin_preview.setAlignment(Qt.AlignCenter)
        self.skin_preview.setMinimumSize(128, 128)
        self.skin_preview.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444; border-radius: 4px;")
        preview_layout.addWidget(self.skin_preview)
        layout.addWidget(preview_group)

        # -- Upload area --
        upload_group = QGroupBox("Upload New Skin")
        upload_layout = QVBoxLayout(upload_group)
        upload_info = QLabel(
            "Select a 64×32 or 64×64 PNG file.\n"
            "The file will be saved as skins/<uuid-with-no-dashes>.png."
        )
        upload_info.setWordWrap(True)
        upload_info.setStyleSheet("color: #cccccc;")
        upload_layout.addWidget(upload_info)

        upload_btn_row = QHBoxLayout()
        self.btn_select_skin = QPushButton("Select PNG File")
        self.btn_select_skin.setMinimumHeight(40)
        self.btn_select_skin.clicked.connect(self._upload_skin)
        upload_btn_row.addWidget(self.btn_select_skin)

        self.btn_remove_skin = QPushButton("🗑 Remove Skin")
        self.btn_remove_skin.setMinimumHeight(40)
        self.btn_remove_skin.setStyleSheet("background-color: #8b0000;")
        self.btn_remove_skin.clicked.connect(self._remove_skin)
        upload_btn_row.addWidget(self.btn_remove_skin)
        upload_btn_row.addStretch()
        upload_layout.addLayout(upload_btn_row)

        layout.addWidget(upload_group)
        layout.addStretch()

        # Load current data after UI is built
        self._refresh_skin_tab()

    def _refresh_skin_tab(self):
        """Re-read player.json and update skin tab display."""
        uuid_raw = ""
        try:
            path = Path("player.json")
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                    uuid_raw = data.get("uuid", "")
        except Exception:
            pass

        if uuid_raw:
            self.skin_uuid_display.setText(uuid_raw)
            # Sanitize: remove dashes
            uuid_clean = uuid_raw.replace("-", "").lower()
            skin_path = Path("skins") / f"{uuid_clean}.png"

            if skin_path.exists():
                self.skin_status.setText("✅ Skin exists")
                self.skin_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #3C8527;")
                # Load preview
                pixmap = QPixmap(str(skin_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.skin_preview.setPixmap(scaled)
                self.btn_remove_skin.setEnabled(True)
            else:
                self.skin_status.setText("❌ No skin file found")
                self.skin_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff5555;")
                self.skin_preview.clear()
                self.skin_preview.setText("No skin loaded")
                self.btn_remove_skin.setEnabled(False)
        else:
            self.skin_uuid_display.setText("(no UUID in player.json)")
            self.skin_status.setText("⚠ UUID not set")
            self.skin_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffaa00;")
            self.skin_preview.clear()
            self.skin_preview.setText("No skin loaded")
            self.btn_remove_skin.setEnabled(False)

    def _upload_skin(self):
        """Open a file dialog and copy the selected PNG to skins/<uuid_clean>.png."""
        # Read UUID from player.json
        uuid_raw = ""
        try:
            path = Path("player.json")
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                    uuid_raw = data.get("uuid", "")
        except Exception:
            pass

        if not uuid_raw:
            QMessageBox.warning(self, "No UUID", "Set a UUID in the Account tab first.")
            self._switch_to_tab(1)
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Skin PNG", "",
            "PNG Images (*.png);;All Files (*)"
        )
        if not file_path:
            return

        # Validate it's a PNG
        if not file_path.lower().endswith(".png"):
            QMessageBox.warning(self, "Invalid File", "Please select a .png file.")
            return

        # Build target path: skins/<uuid_nodashes>.png
        uuid_clean = uuid_raw.replace("-", "").lower()
        target_dir = Path("skins")
        target_dir.mkdir(exist_ok=True)
        target_path = target_dir / f"{uuid_clean}.png"

        # Copy file
        try:
            import shutil
            shutil.copy2(file_path, str(target_path))
            self.log(f"[SKIN] Uploaded skin for {uuid_raw} → {target_path}")
            self._refresh_skin_tab()
            QMessageBox.information(self, "Success", "Skin uploaded successfully!")
        except Exception as e:
            self.log(f"[SKIN ERROR] Failed to copy: {e}")
            QMessageBox.critical(self, "Error", f"Could not save skin:\n{e}")

    def _remove_skin(self):
        """Delete the skin file if it exists."""
        uuid_raw = ""
        try:
            path = Path("player.json")
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                    uuid_raw = data.get("uuid", "")
        except Exception:
            pass

        if not uuid_raw:
            return

        uuid_clean = uuid_raw.replace("-", "").lower()
        target_path = Path("skins") / f"{uuid_clean}.png"

        if target_path.exists():
            reply = QMessageBox.question(
                self, "Confirm Removal",
                f"Delete skin for UUID {uuid_raw}?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    target_path.unlink()
                    self.log(f"[SKIN] Removed skin: {target_path}")
                    self._refresh_skin_tab()
                except Exception as e:
                    self.log(f"[SKIN ERROR] Failed to remove: {e}")
                    QMessageBox.critical(self, "Error", f"Could not remove skin:\n{e}")


    # ---- Logs tab --------------------------------------------------
    def _setup_logs_tab(self):
        layout = QVBoxLayout(self.page_logs)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Launcher Logs")
        title.setStyleSheet("font-size: 20px; color: #ffffff;")
        layout.addWidget(title)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

    # ---- Settings tab -----------------------------------------------
    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Java Executable", "",
                                              "Java Executable (java*);;All Files (*)")
        if path:
            self.java_path_edit.setText(path)

    def _setup_settings_tab(self):
        # ---------------------------------------------------------------
        # Create a scroll area and a content widget
        # ---------------------------------------------------------------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                                  "QScrollBar:vertical { background: #2b2b2b; width: 10px; }"
                                  "QScrollBar::handle:vertical { background: #555; border-radius: 5px; }"
                                  "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        # The content widget will hold all settings elements
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # ---------------------------------------------------------------
        # Now everything you had in the original _setup_settings_tab goes below
        # Just replace the page_layout variable with 'layout'
        # ---------------------------------------------------------------

        title = QLabel("Launch Settings")
        title.setStyleSheet("font-size: 24px; color: #ffffff; margin-bottom: 10px;")
        layout.addWidget(title)

        # ---- Fullscreen ----
        self.fullscreen_check = QCheckBox("Launch in fullscreen mode")
        self.fullscreen_check.setChecked(self.settings.get("fullscreen", True))
        self.fullscreen_check.toggled.connect(self._on_fullscreen_toggled)
        layout.addWidget(self.fullscreen_check)

        self.res_group = QGroupBox("Window Resolution (if not fullscreen)")
        res_layout = QFormLayout(self.res_group)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 3840)
        self.width_spin.setValue(self.settings.get("width", 854))
        self.width_spin.valueChanged.connect(lambda v: self.settings.set("width", v))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 2160)
        self.height_spin.setValue(self.settings.get("height", 480))
        self.height_spin.valueChanged.connect(lambda v: self.settings.set("height", v))
        res_layout.addRow("Width:", self.width_spin)
        res_layout.addRow("Height:", self.height_spin)
        layout.addWidget(self.res_group)
        self._on_fullscreen_toggled(self.fullscreen_check.isChecked())

        # ---- RAM slider ----
        ram_group = QGroupBox("Memory Allocation")
        ram_layout = QVBoxLayout(ram_group)
        total_ram = self._get_total_ram_mb()
        max_ram = max(2048, total_ram)
        max_ram = min(max_ram, 32768)

        slider_row = QHBoxLayout()
        slider_label = QLabel("Max RAM:")
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(2048, max_ram)
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setPageStep(1024)
        self.ram_slider.setValue(self.settings.get("ram_mb", 2048))

        self.ram_value_label = QLabel(f"{self.ram_slider.value()} MB")
        self.ram_value_label.setFixedWidth(100)
        self.ram_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        slider_row.addWidget(slider_label)
        slider_row.addWidget(self.ram_slider, 1)
        slider_row.addWidget(self.ram_value_label)

        self.ram_reset_btn = QPushButton("Defaults (4 GB)")
        self.ram_reset_btn.clicked.connect(self._reset_ram_to_default)

        info_system = QLabel(f"System RAM: {total_ram} MB ({total_ram / 1024:.1f} GB)")
        info_range = QLabel(f"Slider range: 2 GB – {max_ram // 1024} GB")

        ram_layout.addLayout(slider_row)
        ram_layout.addWidget(self.ram_reset_btn)
        ram_layout.addWidget(info_system)
        ram_layout.addWidget(info_range)

        self.ram_slider.valueChanged.connect(self._on_ram_changed)
        layout.addWidget(ram_group)

        # ========== AUTH‑INJECTOR SETTINGS ==========
        authlib_group = QGroupBox("authlib‑injector (Custom Skins)")
        authlib_layout = QVBoxLayout(authlib_group)
        authlib_layout.setSpacing(12)

        path_form = QFormLayout()
        path_form.setSpacing(8)
        path_row = QHBoxLayout()
        self.authlib_path_edit = QLineEdit(self.settings.get("authlib_injector_path", "authlib-injector.jar"))
        self.authlib_path_edit.setMinimumHeight(35)
        self.authlib_path_edit.textChanged.connect(lambda t: self.settings.set("authlib_injector_path", t))
        self.btn_browse_authlib = QPushButton("Browse...")
        self.btn_browse_authlib.clicked.connect(self._browse_authlib)
        path_row.addWidget(self.authlib_path_edit, 1)
        path_row.addWidget(self.btn_browse_authlib)
        path_form.addRow("JAR path:", path_row)
        authlib_layout.addLayout(path_form)

        url_form = QFormLayout()
        url_form.setSpacing(8)
        url_row = QHBoxLayout()
        self.authlib_url_edit = QLineEdit(self.settings.get("authlib_injector_url", "http://localhost:25585"))
        self.authlib_url_edit.setMinimumHeight(35)
        self.authlib_url_edit.textChanged.connect(lambda t: self.settings.set("authlib_injector_url", t))
        url_row.addWidget(self.authlib_url_edit, 1)
        url_form.addRow("Auth server URL:", url_row)
        authlib_layout.addLayout(url_form)

        options_row = QHBoxLayout()
        self.authlib_enabled_check = QCheckBox("Enable authlib‑injector")
        self.authlib_enabled_check.setChecked(self.settings.get("authlib_enabled", True))
        self.authlib_enabled_check.toggled.connect(lambda checked: self.settings.set("authlib_enabled", checked))
        options_row.addWidget(self.authlib_enabled_check)

        self.btn_install_authlib = QPushButton("⬇ Install authlib")
        self.btn_install_authlib.clicked.connect(self._install_authlib)
        self.btn_install_authlib.setFixedHeight(35)
        options_row.addWidget(self.btn_install_authlib)
        options_row.addStretch()
        authlib_layout.addLayout(options_row)

        self.authlib_progress_bar = QProgressBar()
        self.authlib_progress_bar.setValue(0)
        self.authlib_progress_bar.setFixedHeight(12)
        self.authlib_progress_bar.setVisible(False)
        authlib_layout.addWidget(self.authlib_progress_bar)

        info_label = QLabel("Download from: https://github.com/yushijinhun/authlib-injector/releases")
        info_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        authlib_layout.addWidget(info_label)

        layout.addWidget(authlib_group)

        # ---- Extra Java args ----
        java_args_group = QGroupBox("Extra JVM Arguments")
        java_args_layout = QVBoxLayout(java_args_group)
        self.java_args_edit = QLineEdit(self.settings.get("java_args", ""))
        self.java_args_edit.setPlaceholderText("e.g. -XX:+UseG1GC -Dlog4j.configurationFile=...")
        self.java_args_edit.textChanged.connect(lambda text: self.settings.set("java_args", text))
        java_args_layout.addWidget(QLabel("Additional flags (space‑separated):"))
        java_args_layout.addWidget(self.java_args_edit)
        layout.addWidget(java_args_group)

        # ---- Java path ----
        java_group = QGroupBox("Java Runtime")
        java_layout = QVBoxLayout(java_group)
        java_path_layout = QHBoxLayout()
        self.java_path_edit = QLineEdit(self.settings.get("java_path", "java"))
        self.java_path_edit.setMinimumHeight(35)
        self.java_path_edit.textChanged.connect(lambda t: self.settings.set("java_path", t))
        self.btn_browse_java = QPushButton("Browse...")
        self.btn_browse_java.clicked.connect(self._browse_java)
        java_path_layout.addWidget(QLabel("Java executable:"))
        java_path_layout.addWidget(self.java_path_edit, 1)
        java_path_layout.addWidget(self.btn_browse_java)
        java_layout.addLayout(java_path_layout)
        info_label = QLabel("Leave as 'java' to use system default (must be on PATH).")
        info_label.setStyleSheet("color: #888; font-size: 12px;")
        java_layout.addWidget(info_label)
        layout.addWidget(java_group)

        layout.addStretch()  # push everything up

        # ---------------------------------------------------------------
        # Wrap up: set the content widget into the scroll area,
        # then add the scroll area to the page.
        # ---------------------------------------------------------------
        scroll_area.setWidget(content_widget)

        # Clear the page layout and add the scroll area
        page_layout = self.page_settings.layout()
        if page_layout is None:
            page_layout = QVBoxLayout(self.page_settings)
            self.page_settings.setLayout(page_layout)
        else:
            # Remove any existing widgets from the page layout
            while page_layout.count():
                item = page_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        page_layout.addWidget(scroll_area)

    # ---- authlib helpers --------------------------------------------
    def _browse_authlib(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select authlib-injector.jar", "",
                                              "JAR Files (*.jar);;All Files (*)")
        if path:
            self.authlib_path_edit.setText(path)
            self.settings.set("authlib_injector_path", path)

    def _install_authlib(self):
        target = self.authlib_path_edit.text().strip()
        if not target:
            target = "authlib-injector.jar"

        # Convert to absolute path
        target = os.path.abspath(target)
        self.authlib_path_edit.setText(target)

        url = ("https://github.com/yushijinhun/authlib-injector/releases/download/"
               "v1.2.7/authlib-injector-1.2.7.jar")

        self.log("[INFO] Downloading authlib-injector v1.2.7 ...")
        self.log(f"[INFO] Target: {target}")

        self.authlib_progress_bar.setVisible(True)
        self.authlib_progress_bar.setValue(0)
        self.btn_install_authlib.setEnabled(False)
        self.btn_install_authlib.setText("Downloading…")
        QApplication.processEvents()

        self.authlib_dl_thread = AuthlibDownloadThread(url, target)
        self.authlib_dl_thread.progress_signal.connect(self.authlib_progress_bar.setValue)
        self.authlib_dl_thread.finished_signal.connect(self._on_authlib_install_finished)
        self.authlib_dl_thread.error_signal.connect(self._on_authlib_install_error)
        self.authlib_dl_thread.start()

    def _on_authlib_install_finished(self):
        self.authlib_progress_bar.setVisible(False)
        self.btn_install_authlib.setEnabled(True)
        self.btn_install_authlib.setText("⬇ Install authlib")

        target = os.path.abspath(self.authlib_path_edit.text().strip())
        self.authlib_path_edit.setText(target)

        self.settings.set("authlib_injector_path", target)

        self.authlib_enabled_check.setChecked(True)
        self.log(f"[SUCCESS] authlib-injector saved to {target}")

    def _on_authlib_install_error(self, error_msg):
        self.authlib_progress_bar.setVisible(False)
        self.btn_install_authlib.setEnabled(True)
        self.btn_install_authlib.setText("⬇ Install authlib")
        self.log(f"[ERROR] Download failed: {error_msg}")

    # ---- callback helpers -------------------------------------------
    def _on_fullscreen_toggled(self, checked):
        self.width_spin.setEnabled(not checked)
        self.height_spin.setEnabled(not checked)
        self.settings.set("fullscreen", checked)

    def on_versions_fetched(self, versions):
        self.ver_combo.blockSignals(True)
        self.ver_combo.clear()
        if versions:
            self.ver_combo.addItems(versions)
        else:
            self.ver_combo.addItem("1.20.4")
        self.ver_combo.blockSignals(False)
        self.check_version_status(self.ver_combo.currentText())

    def check_version_status(self, version_str):
        if not version_str or version_str == "Loading versions...":
            self.btn_launch.setEnabled(False)
            return
        json_path = self.game_dir / "versions" / version_str / f"{version_str}.json"
        if json_path.exists():
            self.btn_launch.setEnabled(True)
            self.btn_download.setText("Re-Download")
            self.btn_launch.setText("PLAY")
        else:
            self.btn_launch.setEnabled(False)
            self.btn_download.setText("Download")
            self.btn_launch.setText("NOT INSTALLED")

    def log(self, message: str):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_current_file_progress(self, percent: int):
        self.current_file_progress_bar.setValue(percent)

    def update_overall_progress(self, percent: int):
        self.overall_progress_bar.setValue(percent)

    def update_file_index(self, current, total, desc):
        self.file_progress_label.setText(f"File {current}/{total}: {desc}")

    # ---- Player data persistence ------------------------------------
    def load_player_data(self):
        try:
            path = Path("player.json")
            if path.exists():
                with open(path, "r") as f:
                    data = json.load(f)
                    if "username" in data:
                        self.user_input.setText(data["username"])
                    if "uuid" in data:
                        self.uuid_input.setText(data["uuid"])
        except Exception:
            pass

    def save_player_data(self):
        data = {
            "username": self.user_input.text().strip(),
            "uuid": self.uuid_input.text().strip()
        }
        with open("player.json", "w") as f:
            json.dump(data, f, indent=2)

    def generate_uuid(self):
        new_uuid = str(py_uuid.uuid4())
        self.uuid_input.setText(new_uuid)
        self.save_player_data()
        self.log(f"[SUCCESS] Saved new UUID: {new_uuid}")

    # ---- Download & launch ------------------------------------------
    def start_download(self):
        version = self.ver_combo.currentText().strip()
        if not version or version == "Loading versions...":
            self.log("[ERROR] Select a valid version.")
            return
        self.btn_download.setEnabled(False)
        self.btn_launch.setEnabled(False)
        self.overall_progress_bar.setValue(0)
        self.current_file_progress_bar.setValue(0)
        self.file_progress_label.setText("")
        self.log(f"\n[INFO] Starting download thread for {version}...")
        self.downloader_thread = DownloaderThread(version, self.game_dir)
        self.downloader_thread.log_signal.connect(self.log)
        self.downloader_thread.file_progress_signal.connect(self.update_current_file_progress)
        self.downloader_thread.file_index_signal.connect(self.update_file_index)
        self.downloader_thread.overall_progress_signal.connect(self.update_overall_progress)
        self.downloader_thread.finished_signal.connect(self.on_download_finished)
        self.downloader_thread.start()

    def on_download_finished(self):
        self.btn_download.setEnabled(True)
        self.file_progress_label.setText("Download finished.")
        self.check_version_status(self.ver_combo.currentText())

    def start_skin_server(self):
        """Start skin.py in a background thread"""

        def run_skin():
            import skin
            skin.main()  # This will block, but only in this thread

        skin_thread = threading.Thread(target=run_skin, daemon=True)
        skin_thread.start()

        # Wait a moment for server to start
        time.sleep(2)
        return skin_thread

    def launch_game(self):
        username = self.user_input.text().strip()
        version = self.ver_combo.currentText().strip()
        uuid_input = self.uuid_input.text().strip()
        if not username or not uuid_input:
            self.log("[ERROR] Missing Username or UUID! Go to the Account tab.")
            self._switch_to_tab(1)
            return
        self._switch_to_tab(3)  # logs tab (index 3)
        self.log(f"\n[INFO] Launching {version}...")

        # Save current player data before launch
        self.save_player_data()

        # Load latest settings
        self.settings.load()

        fullscreen = self.settings.get("fullscreen", True)
        width = self.settings.get("width", 854)
        height = self.settings.get("height", 480)
        java_path = self.settings.get("java_path", "java")
        ram_mb = self.settings.get("ram_mb", 2048)
        java_args_str = self.settings.get("java_args", "").strip()
        java_args = java_args_str.split() if java_args_str else []

        # Add authlib-injector if enabled
        authlib_enabled = self.settings.get("authlib_enabled", True)
        if authlib_enabled:
            authlib_path = self.settings.get("authlib_injector_path", "authlib-injector.jar")
            authlib_url = self.settings.get("authlib_injector_url", "http://localhost:25585")
            # Check if file exists, show warning if not
            if not Path(authlib_path).exists():
                self.log(f"[WARNING] authlib‑injector.jar not found at: {authlib_path}")
                self.log("[WARNING] Use the 'Install authlib' button in Settings to download it.")
            java_args.insert(0, f"-javaagent:{authlib_path}={authlib_url}")
            java_args.append("-Dauthlibinjector.noShowServerName")
            java_args.append("-Dauthlibinjector.debug=verbose")
            self.log(f"[INFO] Using authlib‑injector: {authlib_path} -> {authlib_url}")

        try:
            self.log("[INFO] Starting skin.py (Yggdrasil auth server)...")
            self.start_skin_server()
        except FileNotFoundError:
            self.log("[WARN] skin.py not found – continuing without it.")
        except Exception as e:
            self.log(f"[WARN] Could not start skin.py: {e}")

        # delete mc skin cache
        skd = os.path.join(os.getcwd(), '.minecraft', 'assets', 'skins')

        try:
            if os.path.exists(skd):
                shutil.rmtree(skd)
                self.log(f"[DEBUG] Successfully deleted: {skd}")
            else:
                self.log(f"[Warn] Directory does not exist (nothing to delete): {skd}")
        except PermissionError:
            self.log(f"[Fail] Permission denied: cannot delete {skd}. Try running as administrator.")
        except Exception as e:
            self.log(f"[Fail] An error occurred: {e}")

        try:
            # Use player.json for authentication
            provider = OfflineAuthProvider(
                cache_path="offline_account.json",
                player_data_path="player.json"
            )
            account = provider.authenticate(username)
            self.log(f"[SUCCESS] Authenticated {account.username}")

            launcher = GameLauncher(
                game_dir=self.game_dir,
                java_path=Path(java_path),
                fullscreen=fullscreen,
                width=width,
                height=height,
                ram_mb=ram_mb,
                java_args=java_args,
            )

            instance_dir = Path(f"./instances/{version}")
            self.game_process = launcher.launch(
                version=version,
                account=account,
                instance_dir=instance_dir,
                log_callback=self.log
            )

            from threading import Thread

            def read_game_output():
                while True:
                    line = self.game_process.stdout.readline()
                    if not line and self.game_process.poll() is not None:
                        break
                    if line:
                        line = line.rstrip('\n')
                        self.log_output.append(line)
                        scrollbar = self.log_output.verticalScrollBar()
                        scrollbar.setValue(scrollbar.maximum())
                self.log("[INFO] Game process terminated.")

            output_thread = Thread(target=read_game_output, daemon=True)
            output_thread.start()
            self.log("[SUCCESS] Game process spawned! Output will appear below.")

        except Exception as e:
            self.log(f"[ERROR] Failed to launch: {str(e)}")

    # ---- system helpers ---------------------------------------------
    def _get_total_ram_mb(self) -> int:
        import ctypes
        system = platform.system()
        try:
            if system == "Windows":
                kernel32 = ctypes.windll.kernel32

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                memoryStatus = MEMORYSTATUSEX()
                memoryStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatus))
                return int(memoryStatus.ullTotalPhys // (1024 * 1024))
            elif system == "Linux":
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            return kb // 1024
            elif system == "Darwin":
                import subprocess
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5
                )
                bytes_ = int(result.stdout.strip())
                return int(bytes_ // (1024 * 1024))
        except Exception:
            pass
        return 8192

    def _on_ram_changed(self, value: int):
        self.ram_value_label.setText(f"{value} MB")
        self.settings.set("ram_mb", value)

    def _reset_ram_to_default(self):
        self.ram_slider.setValue(4096)


def main():
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    window = MinecraftLauncherGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
