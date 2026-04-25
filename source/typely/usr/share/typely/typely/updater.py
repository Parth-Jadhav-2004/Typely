from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QMessageBox

LOGGER = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_RELEASE_URL = "https://github.com/{owner}/{repo}/releases/latest"

# Default repository - can be configured
DEFAULT_REPO_OWNER = "Parth-Jadhav-2004"
DEFAULT_REPO_NAME = "Typely"


class UpdateChecker:
    def __init__(self, owner: str = DEFAULT_REPO_OWNER, repo: str = DEFAULT_REPO_NAME) -> None:
        self.owner = owner
        self.repo = repo
        self._current_version = self._get_installed_version()

    def _get_installed_version(self) -> str:
        """Get the currently installed version from dpkg."""
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", "typely"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception as exc:
            LOGGER.warning("Could not determine installed version: %s", exc)
            return "0.0.0"

    def _fetch_latest_release(self) -> dict | None:
        """Fetch the latest release info from GitHub API."""
        url = GITHUB_API_URL.format(owner=self.owner, repo=self.repo)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Typely-Updater",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            LOGGER.error("Failed to fetch latest release: %s", exc)
            return None

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """Parse version string to tuple for comparison."""
        # Remove leading 'v' if present
        version = version.lstrip("v")
        # Split by dots and convert to integers
        try:
            return tuple(int(x) for x in version.split(".")[:3])
        except ValueError:
            return (0, 0, 0)

    def check_for_update(self) -> tuple[bool, str, str, str | None]:
        """
        Check if an update is available.

        Returns:
            Tuple of (update_available, current_version, latest_version, download_url)
        """
        release = self._fetch_latest_release()
        if release is None:
            return False, self._current_version, "unknown", None

        latest_version = release.get("tag_name", "0.0.0")
        download_url = None

        # Find the .deb asset
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.endswith("_all.deb") or name.endswith(".deb"):
                download_url = asset.get("browser_download_url")
                break

        current_parsed = self._parse_version(self._current_version)
        latest_parsed = self._parse_version(latest_version)

        is_newer = latest_parsed > current_parsed

        return is_newer, self._current_version, latest_version, download_url

    def download_and_install(self, download_url: str, progress_callback: Callable[[int], None]) -> bool:
        """
        Download and install the update.

        Args:
            download_url: URL to download the .deb from
            progress_callback: Called with progress percentage (0-100)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as tmp:
                tmp_path = tmp.name

            req = urllib.request.Request(download_url)
            with urllib.request.urlopen(req, timeout=300) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            progress_callback(progress)

            # Install the package using pkexec (polkit) for privilege escalation
            progress_callback(100)  # Download complete

            # Use pkexec to run dpkg install
            result = subprocess.run(
                ["pkexec", "dpkg", "-i", tmp_path],
                capture_output=True,
                text=True,
            )

            # Clean up
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

            if result.returncode == 0:
                return True
            else:
                LOGGER.error("dpkg install failed: %s", result.stderr)
                return False

        except Exception as exc:
            LOGGER.error("Download and install failed: %s", exc)
            # Clean up on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False


def show_update_dialog(
    parent,
    current_version: str,
    latest_version: str,
    download_url: str | None,
    on_update: Callable[[], None],
) -> bool:
    """
    Show update available dialog.

    Returns:
        True if user wants to update, False otherwise
    """
    msg = QMessageBox(parent)
    msg.setWindowTitle("Update Available")
    msg.setText(f"A new version of Typely is available!")
    msg.setInformativeText(f"Current version: {current_version}\nLatest version: {latest_version}")

    if download_url:
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.button(QMessageBox.StandardButton.Yes).setText("Update Now")
        msg.button(QMessageBox.StandardButton.No).setText("Later")
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    else:
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setInformativeText(
            msg.informativeText() + "\n\nPlease visit GitHub to download the update."
        )

    result = msg.exec()

    if download_url and result == QMessageBox.StandardButton.Yes:
        on_update()
        return True
    return False


def show_update_progress_dialog(parent) -> QMessageBox:
    """Create and return a progress dialog for updates."""
    msg = QMessageBox(parent)
    msg.setWindowTitle("Updating Typely")
    msg.setText("Downloading and installing update...")
    msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
    msg.setMinimumWidth(300)
    return msg


def show_update_result_dialog(parent, success: bool) -> None:
    """Show the result of the update attempt."""
    if success:
        msg = QMessageBox(parent)
        msg.setWindowTitle("Update Complete")
        msg.setText("Typely has been updated successfully!")
        msg.setInformativeText("The application will now restart.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
    else:
        msg = QMessageBox(parent)
        msg.setWindowTitle("Update Failed")
        msg.setText("Failed to update Typely.")
        msg.setInformativeText(
            "Please try downloading the update manually from GitHub."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
