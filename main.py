#!/usr/bin/env python3
import os
import sys
import json
import platform
import threading
import time

import requests
import uuid as py_uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                               QProgressBar, QComboBox, QStackedWidget, QButtonGroup,
                               QCheckBox, QSpinBox, QFileDialog, QGroupBox, QFormLayout,
                               QSlider, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap
from offline import OfflineAuthProvider
from launcher import GameLauncher


# Inline SVGs
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


def create_svg_icon(svg_string):
    byte_array = QByteArray(svg_string.encode('utf-8'))
    pixmap = QPixmap()
    pixmap.loadFromData(byte_array, "SVG")
    return QIcon(pixmap)


def sort_versions(versions):
    """Sort Minecraft version strings from newest to oldest."""
    def version_sort_key(v):
        parts = v.split('.')
        result = []
        for p in parts:
            # Handle snapshot suffixes like "1.20.4-pre1"
            num_part = ''
            suffix_part = ''
            for c in p:
                if c.isdigit():
                    num_part += c
                else:
                    suffix_part += c
            result.append(int(num_part) if num_part else 0)
            # String suffix gets a lower sort priority
            result.append(suffix_part or '')
        return result
    return sorted(versions, key=version_sort_key, reverse=True)


# ---------------------------------------------------------------------------
# Settings
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
            "java_args": ""
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
# Manifest fetcher thread (online)
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
# Downloader thread
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
        nav_layout.addWidget(self.btn_nav_logs)
        nav_layout.addWidget(self.btn_nav_settings)
        nav_layout.addStretch()

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.addButton(self.btn_nav_play, 0)
        self.nav_group.addButton(self.btn_nav_account, 1)
        self.nav_group.addButton(self.btn_nav_logs, 2)
        self.nav_group.addButton(self.btn_nav_settings, 3)
        self.nav_group.buttonClicked.connect(self._nav_clicked)

        # Pages
        self.pages = QStackedWidget()
        self.page_play = QWidget()
        self.page_account = QWidget()
        self.page_logs = QWidget()
        self.page_settings = QWidget()
        self.pages.addWidget(self.page_play)     # 0
        self.pages.addWidget(self.page_account)  # 1
        self.pages.addWidget(self.page_logs)     # 2
        self.pages.addWidget(self.page_settings) # 3

        main_layout.addWidget(nav_widget)
        main_layout.addWidget(self.pages)

        self.btn_nav_play.setChecked(True)
        self.pages.setCurrentIndex(0)

        self._setup_play_tab()
        self._setup_account_tab()
        self._setup_logs_tab()
        self._setup_settings_tab()

        self.downloader_thread = None
        self.load_player_data()
        self.user_input.editingFinished.connect(self.save_player_data)
        self.uuid_input.editingFinished.connect(self.save_player_data)

        # Initial version list
        self.refresh_versions()

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

        # Top row: version label + refresh button
        top_row = QHBoxLayout()
        ver_label = QLabel("Select Version:")
        ver_label.setStyleSheet("font-size: 16px; color: #aaaaaa; margin-bottom: 5px;")
        top_row.addWidget(ver_label)
        top_row.addStretch()
        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setFixedWidth(100)
        self.btn_refresh.setMinimumHeight(30)
        self.btn_refresh.clicked.connect(self.refresh_versions)
        top_row.addWidget(self.btn_refresh)

        layout.addLayout(top_row)

        self.ver_combo = QComboBox()
        self.ver_combo.setEditable(False)
        self.ver_combo.setMinimumHeight(45)
        self.ver_combo.addItem("Loading versions...")
        layout.addWidget(self.ver_combo)

        layout.addSpacing(20)

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
            "Note:\n- Changing UUID may affect server data and world ownership.\n- a UUID Matching Someone Will Not Give You Their Skin"
        )
        warning_label.setStyleSheet(
            "background-color: #3a3a1a; border: 1px solid #ffaa00; border-radius: 6px; padding: 12px; "
            "color: #ffcc00; font-weight: bold; font-size: 13px;"
        )
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
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                                  "QScrollBar:vertical { background: #2b2b2b; width: 10px; }"
                                  "QScrollBar::handle:vertical { background: #555; border-radius: 5px; }"
                                  "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

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

        # ---- Extra Java args ----
        java_args_group = QGroupBox("Extra JVM Arguments")
        java_args_layout = QVBoxLayout(java_args_group)
        self.java_args_edit = QLineEdit(self.settings.get("java_args", ""))
        self.java_args_edit.setPlaceholderText("e.g. -XX:+UseG1GC -Dlog4j.configurationFile=...")
        self.java_args_edit.textChanged.connect(lambda text: self.settings.set("java_args", text))
        java_args_layout.addWidget(QLabel("Additional flags (space‑separated - Make sure what you know what you are doing):"))
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

        layout.addStretch()

        scroll_area.setWidget(content_widget)
        page_layout = self.page_settings.layout()
        if page_layout is None:
            page_layout = QVBoxLayout(self.page_settings)
            self.page_settings.setLayout(page_layout)
        else:
            while page_layout.count():
                item = page_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        page_layout.addWidget(scroll_area)

    # ---- Version refresh (online + local) ---------------------------
    def refresh_versions(self):
        """Fetch online versions and combine with locally installed ones."""
        self.ver_combo.blockSignals(True)
        self.ver_combo.clear()
        self.ver_combo.addItem("Loading versions...")
        self.btn_refresh.setEnabled(False)

        # Start online fetcher in background
        self.fetcher = ManifestFetcherThread()
        self.fetcher.versions_signal.connect(self._on_versions_combined)
        self.fetcher.start()

        # Also read local versions immediately
        local_versions = self._get_local_versions()
        if local_versions:
            self._local_versions = local_versions
        else:
            self._local_versions = []

    def _get_local_versions(self):
        """Return list of version ids that have a JSON file in versions/"""
        versions_dir = self.game_dir / "versions"
        if not versions_dir.exists():
            return []
        result = []
        for folder in versions_dir.iterdir():
            if folder.is_dir():
                ver = folder.name
                if (folder / f"{ver}.json").exists():
                    result.append(ver)
        return result  # Not sorted here; will be sorted in _on_versions_combined

    def _on_versions_combined(self, online_versions):
        """Called when online fetch completes. Merge with local versions."""
        # Combine and deduplicate
        all_versions = list(set(online_versions) | set(self._local_versions))
        # Use proper version sorting
        sorted_versions = sort_versions(all_versions)

        self.ver_combo.blockSignals(True)
        self.ver_combo.clear()
        if sorted_versions:
            self.ver_combo.addItems(sorted_versions)
        else:
            self.ver_combo.addItem("No versions found")
        self.ver_combo.blockSignals(False)
        self.btn_refresh.setEnabled(True)

        # Update status for the current selection
        current = self.ver_combo.currentText()
        if current and current != "No versions found":
            self.check_version_status(current)
        else:
            self.btn_launch.setEnabled(False)
            self.btn_download.setEnabled(False)

    # ---- callback helpers -------------------------------------------
    def _on_fullscreen_toggled(self, checked):
        self.width_spin.setEnabled(not checked)
        self.height_spin.setEnabled(not checked)
        self.settings.set("fullscreen", checked)

    def check_version_status(self, version_str):
        if not version_str or version_str in ("Loading versions...", "No versions found"):
            self.btn_launch.setEnabled(False)
            self.btn_download.setEnabled(False)
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
            self.btn_download.setEnabled(True)

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
        if not version or version in ("Loading versions...", "No versions found"):
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

    def launch_game(self):
        username = self.user_input.text().strip()
        version = self.ver_combo.currentText().strip()
        uuid_input = self.uuid_input.text().strip()
        if not username or not uuid_input:
            self.log("[ERROR] Missing Username or UUID! Go to the Account tab.")
            self._switch_to_tab(1)
            return
        self._switch_to_tab(2)  # logs tab (index 2)
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
