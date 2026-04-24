from __future__ import annotations

import shlex
import sys
from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "typely.desktop"


def build_exec_command(project_root: Path, python_executable: str | None = None) -> str:
    python_bin = python_executable or sys.executable
    return (
        "/bin/sh -lc "
        + shlex.quote(f"cd {shlex.quote(str(project_root))} && {shlex.quote(python_bin)} -m typely")
    )


def render_desktop_entry(exec_command: str, working_dir: Path) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=Typely",
            "Comment=Tray voice-to-text assistant",
            f"Exec={exec_command}",
            f"Path={working_dir}",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            "StartupNotify=false",
            "",
        ]
    )


def is_autostart_enabled(path: Path = AUTOSTART_FILE) -> bool:
    return path.exists()


def enable_autostart(exec_command: str, working_dir: Path, path: Path = AUTOSTART_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_desktop_entry(exec_command=exec_command, working_dir=working_dir)
    path.write_text(content, encoding="utf-8")


def disable_autostart(path: Path = AUTOSTART_FILE) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
