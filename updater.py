import sys
import os
import json
import requests
import tempfile
import shutil
import subprocess
import time
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QSpacerItem,
    QSizePolicy, QWidget, QFileDialog, QStackedWidget
)
from PySide6.QtGui import QPainter, QColor, QFont, QPen

APP_VERSION = "1.0.0"
# ──────────────────────────────────────────────────────────────
# THEME
# ──────────────────────────────────────────────────────────────
GREEN_DARK_STYLE = """
QDialog, QMessageBox {
    background-color: #121212;
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
}
QLabel {
    color: #e0e0e0;
    background: transparent;
}
QPushButton {
    background-color: #1e2e1e;
    color: #a0e0a0;
    border: 1px solid #2a4a2a;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2a3f2a;
    border-color: #44c044;
}
QPushButton:pressed {
    background-color: #182818;
}
QProgressBar {
    border: 1px solid #2a4a2a;
    background-color: #1a1a1a;
    border-radius: 4px;
    text-align: center;
    color: #a0e0a0;
    height: 22px;
}
QProgressBar::chunk {
    background-color: #44c044;
    border-radius: 3px;
}
"""

# ──────────────────────────────────────────────────────────────
# SPINNER WIDGET (no setAlignment needed)
# ──────────────────────────────────────────────────────────────
class SpinnerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(60, 60)
        self.setStyleSheet("background: transparent;")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)

    def _rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#44c044"))
        pen.setWidth(4)
        painter.setPen(pen)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        for i in range(8):
            painter.save()
            painter.rotate(i * 45)
            if i == 0:
                painter.setOpacity(1.0)
            else:
                painter.setOpacity(0.15 + 0.85 * (1 - i / 8))
            painter.drawLine(12, 0, 25, 0)
            painter.restore()
        painter.end()


# ──────────────────────────────────────────────────────────────
# CHECKER THREAD
# ──────────────────────────────────────────────────────────────
class UpdateChecker(QThread):
    update_found = Signal(dict)
    no_update = Signal()
    error = Signal(str)

    def __init__(self, version_url, current_version):
        super().__init__()
        self.version_url = version_url
        self.current_version = current_version

    def run(self):
        try:
            response = requests.get(self.version_url, timeout=10)
            response.raise_for_status()
            try:
                data = response.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                content = response.content.decode('utf-8-sig', errors='ignore')
                content = content.strip().replace('\ufeff', '').replace('\x00', '')
                data = json.loads(content)

            latest = data.get("version")
            if not latest:
                raise ValueError("Missing 'version' key")

            if self._is_newer(latest):
                self.update_found.emit(data)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _is_newer(self, latest_version):
        try:
            cur = list(map(int, self.current_version.split('.')))
            lat = list(map(int, latest_version.split('.')))
            max_len = max(len(cur), len(lat))
            cur += [0] * (max_len - len(cur))
            lat += [0] * (max_len - len(lat))
            return lat > cur
        except:
            return latest_version > self.current_version


# ──────────────────────────────────────────────────────────────
# DOWNLOADER THREAD
# ──────────────────────────────────────────────────────────────
class UpdateDownloader(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            temp_dir = Path(tempfile.gettempdir()) / "mcl_updater"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dl_path = temp_dir / "update.exe"

            self.progress.emit(0, "Starting download…")
            response = requests.get(self.download_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(dl_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            self.progress.emit(pct, f"Downloading… {pct}%")
            self.progress.emit(100, "Download complete!")
            self.finished.emit(str(dl_path))
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────
# MAIN DIALOG
# ──────────────────────────────────────────────────────────────
class UpdateDialog(QDialog):
    def __init__(self, parent=None, version_url=None, current_version=None):
        super().__init__(parent)
        self.version_url = version_url or "https://raw.githubusercontent.com/radin6262/MCL/main/version.json"
        self.current_version = current_version or self._read_local_version()
        self.update_info = None
        self.download_path = None
        self._is_script = not getattr(sys, 'frozen', False)

        self._setup_stacked_pages()
        self.setStyleSheet(GREEN_DARK_STYLE)
        self.setWindowTitle("Launcher Updater")
        self.setFixedSize(480, 340)
        self._start_check()

    def _read_local_version(self):
        return APP_VERSION

    # ── stacked pages ──
    def _setup_stacked_pages(self):
        main_layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Page 0 – Checking
        page_check = QWidget()
        pc_layout = QVBoxLayout(page_check)
        pc_layout.addStretch()

        # Spinner widget - alignment via layout, not widget
        spinner_container = QVBoxLayout()
        spinner_container.setAlignment(Qt.AlignCenter)
        self.spinner = SpinnerWidget()
        spinner_container.addWidget(self.spinner)
        pc_layout.addLayout(spinner_container)

        self.check_label = QLabel("Checking for updates…")
        self.check_label.setAlignment(Qt.AlignCenter)
        self.check_label.setStyleSheet("font-size: 14px; color: #a0e0a0; margin-top: 10px;")
        pc_layout.addWidget(self.check_label)
        pc_layout.addStretch()
        self.stack.addWidget(page_check)  # index 0

        # Page 1 – Update available
        page_update = QWidget()
        pu_layout = QVBoxLayout(page_update)
        pu_layout.addStretch()
        self.update_title = QLabel()
        self.update_title.setStyleSheet("font-size: 18px; color: #ffffff; font-weight: bold;")
        self.update_title.setAlignment(Qt.AlignCenter)
        pu_layout.addWidget(self.update_title)
        self.update_desc = QLabel()
        self.update_desc.setWordWrap(True)
        self.update_desc.setAlignment(Qt.AlignCenter)
        self.update_desc.setStyleSheet("color: #b0b0b0; margin: 10px 0;")
        pu_layout.addWidget(self.update_desc)
        self.download_btn = QPushButton("Download Update")
        self.download_btn.setFixedWidth(200)
        self.download_btn.clicked.connect(self._start_download)
        pu_layout.addWidget(self.download_btn, 0, Qt.AlignCenter)
        pu_layout.addStretch()
        self.stack.addWidget(page_update)  # index 1

        # Page 2 – Download progress
        page_dl = QWidget()
        pdl_layout = QVBoxLayout(page_dl)
        pdl_layout.addStretch()
        dl_title = QLabel("Downloading…")
        dl_title.setAlignment(Qt.AlignCenter)
        dl_title.setStyleSheet("font-size: 16px; color: #a0e0a0;")
        pdl_layout.addWidget(dl_title)
        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 100)
        pdl_layout.addWidget(self.dl_progress)
        self.dl_status = QLabel("Waiting…")
        self.dl_status.setAlignment(Qt.AlignCenter)
        self.dl_status.setStyleSheet("color: #b0b0b0;")
        pdl_layout.addWidget(self.dl_status)
        pdl_layout.addStretch()
        self.stack.addWidget(page_dl)  # index 2

        # Page 3 – Up to date
        page_done = QWidget()
        pd_layout = QVBoxLayout(page_done)
        pd_layout.addStretch()
        up_to_date = QLabel("✓ You already have the latest version.")
        up_to_date.setAlignment(Qt.AlignCenter)
        up_to_date.setStyleSheet("font-size: 15px; color: #44c044;")
        pd_layout.addWidget(up_to_date)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        pd_layout.addWidget(close_btn, 0, Qt.AlignCenter)
        pd_layout.addStretch()
        self.stack.addWidget(page_done)  # index 3

        # Page 4 – Error
        page_err = QWidget()
        pe_layout = QVBoxLayout(page_err)
        pe_layout.addStretch()
        self.err_label = QLabel()
        self.err_label.setAlignment(Qt.AlignCenter)
        self.err_label.setWordWrap(True)
        self.err_label.setStyleSheet("color: #ff6b6b; font-size: 13px;")
        pe_layout.addWidget(self.err_label)
        retry_btn = QPushButton("Retry")
        retry_btn.clicked.connect(lambda: self._start_check())
        pe_layout.addWidget(retry_btn, 0, Qt.AlignCenter)
        pe_layout.addStretch()
        self.stack.addWidget(page_err)  # index 4

    # ── State transitions ──
    def _start_check(self):
        self.stack.setCurrentIndex(0)
        self.check_label.setText("Checking for updates…")
        self.checker = UpdateChecker(self.version_url, self.current_version)
        self.checker.update_found.connect(self._on_update_found)
        self.checker.no_update.connect(self._on_no_update)
        self.checker.error.connect(self._on_check_error)
        self.checker.start()

    def _on_update_found(self, info):
        self.update_info = info
        ver = info.get("version", "?")
        changelog = info.get("changelog", "")
        self.update_title.setText(f"Version {ver} available")
        self.update_desc.setText(changelog if changelog else "A new version is ready.")
        self.stack.setCurrentIndex(1)

    def _on_no_update(self):
        self.stack.setCurrentIndex(3)

    def _on_check_error(self, err):
        self.err_label.setText(f"Update check failed:\n{err}")
        self.stack.setCurrentIndex(4)

    def _start_download(self):
        if self._is_script:
            if not self._script_warning():
                return
        url = self.update_info.get("download_url")
        if not url:
            QMessageBox.warning(self, "Error", "No download URL provided.")
            return
        self.stack.setCurrentIndex(2)
        self.dl_progress.setValue(0)
        self.dl_status.setText("Starting download…")
        self.downloader = UpdateDownloader(url)
        self.downloader.progress.connect(self._on_dl_progress)
        self.downloader.finished.connect(self._on_dl_finished)
        self.downloader.error.connect(self._on_dl_error)
        self.downloader.start()

    def _script_warning(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Script Detected")
        msg.setIcon(QMessageBox.Warning)
        msg.setText("You are running this program as a Python script.")
        msg.setInformativeText(
            "Automatic updates only work with the compiled executable.\n\n"
            "If you continue, the new .exe will be downloaded to a location you choose.\n"
            "You must replace the old launcher manually."
        )
        msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Cancel)
        msg.button(QMessageBox.Ok).setText("Continue (Download .exe)")
        msg.button(QMessageBox.Cancel).setText("Cancel")
        msg.setStyleSheet(GREEN_DARK_STYLE)
        return msg.exec() == QMessageBox.Ok

    def _on_dl_progress(self, pct, status):
        self.dl_progress.setValue(pct)
        self.dl_status.setText(status)

    def _on_dl_finished(self, file_path):
        self.download_path = file_path
        if self._is_script:
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save the new launcher",
                str(Path.home() / "Downloads" / "launcher_update.exe"),
                "Executable (*.exe)"
            )
            if save_path:
                shutil.copy2(file_path, save_path)
                QMessageBox.information(
                    self, "Download Complete",
                    f"Saved to:\n{save_path}\n\nReplace your old launcher manually."
                )
            else:
                QMessageBox.warning(self, "Cancelled", "File was not saved.")
            self.accept()
        else:
            self._do_install()

    def _on_dl_error(self, err):
        QMessageBox.critical(self, "Download Error", err)
        self.stack.setCurrentIndex(1)

    def _do_install(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Ready to Update")
        msg.setText("The launcher will now close and update.")
        msg.setInformativeText("It will restart automatically after the update.")
        msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        msg.button(QMessageBox.Ok).setText("Continue Update")
        msg.button(QMessageBox.Cancel).setText("Cancel")
        msg.setStyleSheet(GREEN_DARK_STYLE)
        if msg.exec() == QMessageBox.Ok:
            self._perform_update()
            self.accept()

    def _perform_update(self):
        """Copy downloaded update over current exe and restart – no .bat file."""
        current_exe = sys.executable
        new_exe = self.download_path

        # Build a single cmd command that waits, copies, cleans up, then restarts
        cmd = (
            f'timeout /t 5 /nobreak >nul && '
            f'copy /Y "{new_exe}" "{current_exe}" && '
            f'del "{new_exe}" && '
            f'start "" "{current_exe}"'
        )


# ──────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION (renamed to match your import)
# ──────────────────────────────────────────────────────────────
def check_updates(parent=None):
    """Show the updater dialog. Returns after dialog is closed."""
    dlg = UpdateDialog(parent)
    dlg.exec()
