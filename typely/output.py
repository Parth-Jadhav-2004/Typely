from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

PasteMode = Literal["cursor_paste", "clipboard_only"]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class EmitResult:
    success: bool
    message: str


class OutputSink:
    def __init__(self) -> None:
        self.has_xclip = shutil.which("xclip") is not None
        self.has_xdotool = shutil.which("xdotool") is not None

    def capture_active_window(self) -> str | None:
        if not self.has_xdotool:
            LOGGER.info("Output: xdotool not available, cannot capture active window")
            return None
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except subprocess.SubprocessError:
            LOGGER.warning("Output: failed to read active window via xdotool")
            return None
        window_id = result.stdout.strip()
        LOGGER.info("Output: captured active window id=%s", window_id or "none")
        return window_id or None

    def emit(self, text: str, mode: PasteMode, target_window_id: str | None = None) -> EmitResult:
        LOGGER.info("Output: emit requested mode=%s chars=%d target_window=%s", mode, len(text), target_window_id or "none")
        if not text.strip():
            return EmitResult(False, "Transcript is empty")

        if not self.has_xclip:
            return EmitResult(False, "xclip is missing; cannot write clipboard")

        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.SubprocessError as exc:
            return EmitResult(False, f"Failed to copy text to clipboard: {exc}")

        if mode == "clipboard_only":
            LOGGER.info("Output: copied to clipboard only")
            return EmitResult(True, "Copied transcript to clipboard")

        if not self.has_xdotool:
            LOGGER.warning("Output: xdotool missing, cannot auto-paste")
            return EmitResult(True, "Copied transcript to clipboard (xdotool missing for auto-paste)")

        if target_window_id:
            try:
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", target_window_id],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.SubprocessError:
                pass

        for combo in (["ctrl+shift+v"], ["ctrl+v"]):
            try:
                command = ["xdotool", "key", "--clearmodifiers"]
                if target_window_id:
                    command.extend(["--window", target_window_id])
                command.extend(combo)
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                LOGGER.info("Output: pasted transcript using combo=%s", "+".join(combo))
                return EmitResult(True, "Pasted transcript at cursor")
            except subprocess.SubprocessError:
                continue

        LOGGER.warning("Output: auto-paste did not trigger, clipboard still updated")
        return EmitResult(True, "Copied transcript to clipboard (auto-paste did not trigger)")
