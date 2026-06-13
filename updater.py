import sys
import os
import json
import requests
import tempfile
import shutil
import subprocess
import threading
import time
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QSpacerItem,
    QSizePolicy, QWidget
)


class UpdateChecker(QThread):
    """Background thread to check for updates"""
    update_found = Signal(dict)
    no_update = Signal()
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, version_url, current_version):
        super().__init__()
        self.version_url = version_url
        self.current_version = current_version

    def run(self):
        try:
            self.progress.emit("Checking for updates...")

            # Fetch version info
            response = requests.get(self.version_url, timeout=10)
            response.raise_for_status()

            latest_info = response.json()
            latest_version = latest_info.get("version")

            if self.is_newer_version(latest_version):
                self.update_found.emit(latest_info)
            else:
                self.no_update.emit()

        except Exception as e:
            self.error.emit(f"Failed to check for updates: {str(e)}")

    def is_newer_version(self, latest_version):
        """Compare version strings (simple numeric comparison)"""
        try:
            # Convert versions to tuples of integers
            current_parts = list(map(int, self.current_version.split('.')))
            latest_parts = list(map(int, latest_version.split('.')))

            # Pad with zeros if needed
            max_len = max(len(current_parts), len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))

            return latest_parts > current_parts
        except:
            # Fallback: string comparison
            return latest_version > self.current_version


class UpdateDownloader(QThread):
    """Background thread to download update"""
    progress = Signal(int, str)  # percentage, status
    finished = Signal(str)  # downloaded file path
    error = Signal(str)

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            # Create temp directory
            temp_dir = Path(tempfile.gettempdir()) / "mcl_updater"
            temp_dir.mkdir(parents=True, exist_ok=True)

            download_path = temp_dir / "update.exe"

            self.progress.emit(0, "Starting download...")

            # Stream download with progress
            response = requests.get(self.download_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent, f"Downloading... {percent}%")

            self.progress.emit(100, "Download complete!")
            self.finished.emit(str(download_path))

        except Exception as e:
            self.error.emit(f"Download failed: {str(e)}")


class UpdateDialog(QDialog):
    """Dialog for update confirmation and progress"""

    def __init__(self, parent=None, update_info=None):
        super().__init__(parent)
        self.update_info = update_info
        self.downloaded_path = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Update Available")
        self.setFixedSize(400, 300)

        layout = QVBoxLayout()

        # Title
        title = QLabel("An update is available!")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Version info
        if self.update_info:
            version_label = QLabel(f"Version {self.update_info.get('version', '')}")
            version_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(version_label)

            changelog = QLabel(self.update_info.get('changelog', ''))
            changelog.setWordWrap(True)
            changelog.setAlignment(Qt.AlignCenter)
            layout.addWidget(changelog)

        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Buttons
        button_layout = QHBoxLayout()

        self.yes_btn = QPushButton("Yes, Update Now")
        self.yes_btn.clicked.connect(self.start_update)
        button_layout.addWidget(self.yes_btn)

        self.no_btn = QPushButton("No, Later")
        self.no_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.no_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def start_update(self):
        """Start the update download process"""
        # Hide confirmation buttons
        self.yes_btn.hide()
        self.no_btn.hide()

        # Show progress bar
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel("Preparing download...")
        self.progress_label.setAlignment(Qt.AlignCenter)

        layout = self.layout()
        layout.insertWidget(layout.count() - 1, self.progress_label)
        layout.insertWidget(layout.count() - 1, self.progress_bar)

        # Start download
        self.downloader = UpdateDownloader(self.update_info['download_url'])
        self.downloader.progress.connect(self.on_download_progress)
        self.downloader.finished.connect(self.on_download_finished)
        self.downloader.error.connect(self.on_download_error)
        self.downloader.start()

    def on_download_progress(self, percent, status):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(status)

    def on_download_finished(self, file_path):
        self.downloaded_path = file_path
        self.show_final_confirmation()

    def on_download_error(self, error_msg):
        QMessageBox.critical(self, "Download Error", error_msg)
        self.reject()

    def show_final_confirmation(self):
        """Show final confirmation before restart"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Ready to Update")
        msg.setText("To continue the update, we need to close this application.")
        msg.setInformativeText("The application will restart automatically after the update.")
        msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        msg.button(QMessageBox.Ok).setText("Continue Update")
        msg.button(QMessageBox.Cancel).setText("Cancel Update")

        result = msg.exec()

        if result == QMessageBox.Ok:
            self.create_update_batch()
            self.accept()  # Close dialog and trigger update
        else:
            self.reject()

    def create_update_batch(self):
        """Create batch file to handle update"""
        current_exe = sys.executable if hasattr(sys, 'frozen') else sys.argv[0]
        current_dir = Path(current_exe).parent

        # Create batch file content
        batch_content = f"""@echo off
chcp 65001 >nul
echo Updating launcher...
timeout /t 2 /nobreak >nul

REM Wait for main process to close
:waitloop
tasklist /FI "IMAGENAME eq {Path(current_exe).name}" 2>nul | find /I "{Path(current_exe).name}" >nul
if %ERRORLEVEL%==0 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

REM Copy new version
copy "{self.downloaded_path}" "{current_exe}" /Y

REM Cleanup
del "{self.downloaded_path}" >nul 2>&1
del "%~f0" >nul 2>&1

REM Restart
start "" "{current_exe}"
"""

        batch_path = current_dir / "updatehelper.bat"
        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)

        return batch_path


class Updater:
    """Main updater class"""

    def __init__(self, parent=None):
        self.parent = parent
        self.current_version = self._get_local_version()
        self.version_url = "https://raw.githubusercontent.com/radin6262/MCL/main/version.json"

    def _get_local_version(self):
        """
        Read current version from a plain text file named 'version'
        (no extension) in the application directory.
        """
        try:
            # Determine base path (works for both script and frozen exe)
            if hasattr(sys, 'frozen'):
                base_path = Path(sys.executable).parent
            else:
                base_path = Path(__file__).parent

            version_file = base_path / "version"  # Plain text file, no .json extension
            if version_file.exists():
                with open(version_file, 'r', encoding='utf-8') as f:
                    version = f.read().strip()
                    if version:  # Ensure it's not empty
                        print(f"Local version: {version}")
                        return version
            else:
                print(f"Local version file not found at {version_file}, using default 1.0.0")
        except Exception as e:
            print(f"Error reading local version file: {e}")

        return "1.0.0"  # Fallback default

    def check_for_updates(self, silent=False):
        """Check for updates and show dialog if found"""
        self.checker = UpdateChecker(self.version_url, self.current_version)

        if not silent:
            # Show checking dialog
            self.checking_dialog = QDialog(self.parent)
            self.checking_dialog.setWindowTitle("Checking for Updates")
            self.checking_dialog.setFixedSize(300, 100)

            layout = QVBoxLayout()
            layout.addWidget(QLabel("Checking for updates..."))

            spinner = QLabel("⏳")
            spinner.setAlignment(Qt.AlignCenter)
            spinner.setStyleSheet("font-size: IIIpx;")
            layout.addWidget(spinner)

            self.checking_dialog.setLayout(layout)
            self.checking_dialog.show()

        # Connect signals
        self.checker.update_found.connect(lambda info: self.on_update_found(info, silent))
        self.checker.no_update.connect(lambda: self.on_no_update(silent))
        self.checker.error.connect(lambda err: self.on_check_error(err, silent))

        self.checker.start()

    def on_update_found(self, update_info, silent):
        """Handle when update is found"""
        if hasattr(self, 'checking_dialog'):
            self.checking_dialog.close()

        if not silent:
            dialog = UpdateDialog(self.parent, update_info)
            if dialog.exec() == QDialog.Accepted:
                self.perform_update(dialog.downloaded_path)
        else:
            # In silent mode, just return the update info
            return update_info

    def on_no_update(self, silent):
        """Handle when no update is found"""
        if hasattr(self, 'checking_dialog'):
            self.checking_dialog.close()

        if not silent:
            QMessageBox.information(self.parent, "Up to Date",
                                    "You're running the latest version!")

    def on_check_error(self, error_msg, silent):
        """Handle check error"""
        if hasattr(self, 'checking_dialog'):
            self.checking_dialog.close()

        if not silent:
            QMessageBox.warning(self.parent, "Update Check Failed", error_msg)

    def perform_update(self, downloaded_path):
        """Execute the update process"""
        if not downloaded_path:
            return

        batch_path = self.create_update_batch(downloaded_path)

        # Launch batch file
        try:
            subprocess.Popen(['cmd', '/c', str(batch_path)],
                             creationflags=subprocess.CREATE_NO_WINDOW)

            # Close application
            if self.parent:
                self.parent.close()
            else:
                sys.exit(0)

        except Exception as e:
            QMessageBox.critical(None, "Update Error",
                                 f"Failed to start update: {str(e)}")

    def create_update_batch(self, downloaded_path):
        """Create batch file for update"""
        current_exe = sys.executable if hasattr(sys, 'frozen') else sys.argv[0]
        current_dir = Path(current_exe).parent

        batch_content = f"""@echo off
chcp 65001 >nul
echo Waiting for launcher to close...
timeout /t 3 /nobreak >nul

:waitloop
tasklist /FI "IMAGENAME eq {Path(current_exe).name}" 2>nul | find /I "{Path(current_exe).name}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

echo Updating...
copy "{downloaded_path}" "{current_exe}" /Y

REM Cleanup
del "{downloaded_path}" >nul 2>&1
del "%~f0" >nul 2>&1

echo Restarting...
start "" "{current_exe}"
"""

        batch_path = current_dir / "updatehelper.bat"
        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)

        return batch_path


# Convenience function for main.py
def check_updates(parent=None, silent=False):
    """Simple function to check for updates"""
    updater = Updater(parent)
    return updater.check_for_updates(silent)


# For testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    updater = Updater()
    updater.check_for_updates()
    sys.exit(app.exec())
