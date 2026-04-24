from __future__ import annotations

import logging
import os
import threading
import math
import audioop
from collections.abc import Callable
from pathlib import Path

from Xlib import display as xdisplay
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from typely.audio import AudioRecorder, list_input_devices
from typely.autostart import build_exec_command, disable_autostart, enable_autostart, is_autostart_enabled
from typely.config import AppConfig, load_config, save_config
from typely.hotkeys import GlobalHotkeyManager, hotkeys_collide, mode_allows, parse_hotkey
from typely.models import MODEL_REGISTRY, ModelManager
from typely.output import OutputSink
from typely.transcribe import Transcriber
from typely.tray import TypelyTray
from typely.vad import SilenceDetector

LOGGER = logging.getLogger(__name__)


class TypelyControlWindow(QWidget):
    def __init__(self, on_toggle: Callable[[], None], on_hide: Callable[[], None], on_quit: Callable[[], None]) -> None:
        super().__init__()
        self._on_toggle = on_toggle
        self._on_hide = on_hide
        self._on_quit = on_quit

        self.setWindowTitle("Typely")
        self.resize(460, 220)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Status: Idle", self)
        self.info_label = QLabel(
            "Hotkeys: Toggle Ctrl+Shift+Space | Hold Ctrl+Alt+Shift+Space\n"
            "Use tray menu for model/provider/microphone/output settings.",
            self,
        )
        self.info_label.setWordWrap(True)

        buttons = QHBoxLayout()
        self.toggle_button = QPushButton("Start Listening", self)
        self.toggle_button.clicked.connect(self._on_toggle)
        hide_button = QPushButton("Hide", self)
        hide_button.clicked.connect(self._on_hide)
        quit_button = QPushButton("Quit", self)
        quit_button.clicked.connect(self._on_quit)

        buttons.addWidget(self.toggle_button)
        buttons.addWidget(hide_button)
        buttons.addWidget(quit_button)

        layout.addWidget(self.status_label)
        layout.addWidget(self.info_label)
        layout.addLayout(buttons)

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"Status: {text}")

    def set_listening(self, listening: bool) -> None:
        self.toggle_button.setText("Stop Listening" if listening else "Start Listening")
        self.set_status("Listening" if listening else "Idle")


class RecordingCapsule(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Typely Recording Indicator")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setFixedSize(132, 44)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 220); border-radius: 14px;")

        self._target_level = 0.0
        self._display_level = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        self._target_level = 0.0
        self._display_level = 0.0
        self._phase = 0.0
        self._timer.start()
        self.show_at_top_center()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, float(level)))

    def _on_tick(self) -> None:
        self._display_level = max(self._target_level, self._display_level * 0.84)
        self._phase += 0.35
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 235))

        left = 12
        width = self.width() - 24
        height = self.height() - 16
        top = 8
        bars = 9
        gap = 4
        bar_width = (width - gap * (bars - 1)) / bars
        min_h = 4.0
        max_h = max(min_h, float(height))
        center_y = top + height / 2.0

        for idx in range(bars):
            envelope = 0.62 + 0.38 * math.sin(self._phase + idx * 0.6)
            amplitude = min_h + (max_h - min_h) * self._display_level * max(0.15, envelope)
            x_pos = left + idx * (bar_width + gap)
            y_pos = center_y - amplitude / 2.0
            painter.drawRoundedRect(int(x_pos), int(y_pos), int(bar_width), int(amplitude), 2, 2)

    def show_at_top_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            x_pos = geometry.x() + (geometry.width() - self.width()) // 2
            y_pos = geometry.y() + 24
            self.move(x_pos, y_pos)
        self.show()


class TypelyController(QObject):
    DEFAULT_TOGGLE_HOTKEY = "Ctrl+Shift+Space"
    DEFAULT_HOLD_HOTKEY = "Ctrl+Alt+Shift+Space"

    toggle_pressed = Signal()
    hold_pressed = Signal()
    hold_released = Signal()
    auto_stop = Signal()
    audio_level = Signal(float)
    model_update = Signal(str, str, str)
    notify_user = Signal(str, str)
    error_user = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.config = load_config()

        self.model_manager = ModelManager()
        self.transcriber = Transcriber(self.model_manager)
        self.output = OutputSink()
        self.vad = SilenceDetector(silence_ms=self.config.silence_autostop_ms)
        self.recorder = AudioRecorder(on_frame=self._on_audio_frame)

        self._transcribing = False
        self._autostop_requested = False
        self._state_lock = threading.RLock()
        self._target_window_id: str | None = None
        self._download_labels: dict[str, QLabel] = {}
        self._download_buttons: dict[str, QPushButton] = {}
        self._download_dialog: QDialog | None = None
        self.control_window = TypelyControlWindow(
            on_toggle=self.toggle_listening,
            on_hide=lambda: self.control_window.hide(),
            on_quit=self.shutdown,
        )
        self.recording_capsule = RecordingCapsule()
        self.control_window.info_label.setText(
            "Hotkeys: Toggle "
            f"{self.config.hotkey_toggle} | Hold {self.config.hotkey_hold}\n"
            "Use tray menu for model/provider/microphone/output settings."
        )

        self.tray = TypelyTray(
            app=app,
            config=self.config,
            on_toggle_listening=self.toggle_listening,
            on_record_mode_change=self.set_record_mode,
            on_model_change=self.set_default_model,
            on_download_models=self.open_model_download_dialog,
            on_open_window=self.show_control_window,
            on_set_toggle_hotkey=self.set_toggle_hotkey,
            on_set_hold_hotkey=self.set_hold_hotkey,
            on_reset_hotkeys=self.reset_hotkeys,
            on_paste_mode_change=self.set_paste_mode,
            on_audio_device_change=self.set_audio_device,
            on_refresh_audio_devices=self.refresh_audio_devices,
            on_silence_enabled_change=self.set_silence_autostop,
            on_silence_timeout_change=self.set_silence_timeout,
            autostart_enabled=is_autostart_enabled(),
            on_autostart_change=self.set_autostart_enabled,
            on_quit=self.shutdown,
        )

        self.toggle_pressed.connect(self._on_toggle_pressed)
        self.hold_pressed.connect(self._on_hold_pressed)
        self.hold_released.connect(self._on_hold_released)
        self.auto_stop.connect(self._on_auto_stop)
        self.audio_level.connect(self.recording_capsule.set_level)
        self.model_update.connect(self._on_model_update)
        self.notify_user.connect(self.tray.notify)
        self.error_user.connect(self._on_error)

        self.hotkeys = GlobalHotkeyManager(
            toggle_hotkey=self.config.hotkey_toggle,
            hold_hotkey=self.config.hotkey_hold,
            record_mode=self.config.record_mode,
            on_toggle_press=lambda: self.toggle_pressed.emit(),
            on_hold_press=lambda: self.hold_pressed.emit(),
            on_hold_release=lambda: self.hold_released.emit(),
            on_error=lambda msg: self.error_user.emit(msg),
        )

    def start(self) -> None:
        LOGGER.info("Typely starting: record_mode=%s paste_mode=%s", self.config.record_mode, self.config.paste_mode)
        self.hotkeys.start()
        self.refresh_audio_devices()
        if not self.tray.is_available():
            LOGGER.warning("System tray unavailable; opening control window")
            self.show_control_window()
            self.control_window.set_status("Tray unavailable")
            self.control_window.info_label.setText(
                "System tray is unavailable in this desktop session.\n"
                "Use this window to control Typely."
            )
        else:
            LOGGER.info("System tray available; app running hidden")
            self.tray.notify("Typely", "Running in tray")

    def show_control_window(self) -> None:
        self.control_window.show()
        self.control_window.raise_()
        self.control_window.activateWindow()

    def shutdown(self) -> None:
        try:
            if self.recorder.running:
                self.recorder.stop()
        except Exception:  # noqa: BLE001
            pass

        self.hotkeys.stop()
        save_config(self.config)
        self.recording_capsule.stop()
        self.tray.close()
        self.app.quit()

    def _save_config(self) -> None:
        save_config(self.config)

    def _on_error(self, message: str) -> None:
        LOGGER.error("Typely error: %s", message)
        self.recording_capsule.stop()
        self.tray.set_status("Error")
        self.control_window.set_status("Error")
        self.tray.notify("Typely Error", message)

    def toggle_listening(self) -> None:
        with self._state_lock:
            if self._transcribing:
                return
            should_stop = self.recorder.running
        if should_stop:
            self.stop_listening_and_transcribe(reason="manual")
        else:
            self.start_listening(reason="manual")

    def _on_toggle_pressed(self) -> None:
        if not mode_allows(self.config.record_mode, "toggle"):
            return
        self.toggle_listening()

    def _on_hold_pressed(self) -> None:
        if not mode_allows(self.config.record_mode, "hold"):
            return
        with self._state_lock:
            if self._transcribing:
                return
            should_start = not self.recorder.running
        if should_start:
            self.start_listening(reason="hold")

    def _on_hold_released(self) -> None:
        if not mode_allows(self.config.record_mode, "hold"):
            return
        with self._state_lock:
            should_stop = self.recorder.running
        if should_stop:
            self.stop_listening_and_transcribe(reason="hold")

    def _on_auto_stop(self) -> None:
        with self._state_lock:
            should_stop = self.recorder.running
        if should_stop:
            self.stop_listening_and_transcribe(reason="silence")

    def _on_audio_frame(self, pcm_chunk: bytes) -> None:
        if not self.recorder.running:
            return
        try:
            rms = audioop.rms(pcm_chunk, 2)
            level = min(1.0, rms / 12000.0)
            self.audio_level.emit(level)
        except Exception:  # noqa: BLE001
            pass
        if not self.config.silence_autostop_enabled:
            return
        if self._autostop_requested:
            return

        if self.vad.feed(pcm_chunk):
            return

        if self.vad.should_stop():
            self._autostop_requested = True
            self.auto_stop.emit()

    def start_listening(self, reason: str) -> None:
        with self._state_lock:
            if self._transcribing or self.recorder.running:
                return
            self._autostop_requested = False
            self.vad.reset()
        try:
            self._target_window_id = self.output.capture_active_window()
            self.recorder.start(device=self.config.audio_device)
        except Exception as exc:  # noqa: BLE001
            self.error_user.emit(f"Microphone start failed: {exc}")
            return

        LOGGER.info("Listening started: reason=%s device=%s target_window=%s", reason, self.config.audio_device, self._target_window_id or "none")
        self.tray.set_listening(True)
        self.control_window.set_listening(True)
        self.recording_capsule.start()
        self.tray.notify("Typely", f"Listening started ({reason})")

    def stop_listening_and_transcribe(self, reason: str) -> None:
        with self._state_lock:
            if self._transcribing or not self.recorder.running:
                return
            self._transcribing = True
        try:
            audio_path = self.recorder.stop()
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._transcribing = False
            self.error_user.emit(f"Failed to stop recorder: {exc}")
            return

        LOGGER.info("Listening stopped: reason=%s audio_path=%s", reason, audio_path)
        self.tray.set_listening(False)
        self.control_window.set_listening(False)
        self.recording_capsule.stop()
        self.tray.set_busy(True)
        self.control_window.set_status("Transcribing")

        thread = threading.Thread(
            target=self._transcribe_worker,
            args=(audio_path, reason),
            daemon=True,
        )
        thread.start()

    def _transcribe_worker(self, audio_path: Path, reason: str) -> None:
        try:
            result = self.transcriber.transcribe(audio_path, self.config.default_model, language=None)
            LOGGER.info(
                "Transcription complete: model=%s language=%s duration=%.2fs chars=%d",
                self.config.default_model,
                result.language,
                result.duration,
                len(result.text),
            )
            emit_result = self.output.emit(result.text, self.config.paste_mode, target_window_id=self._target_window_id)
            LOGGER.info("Output result: success=%s message=%s", emit_result.success, emit_result.message)

            if result.text:
                provider_model = self.config.default_model
                if result.duration > 0:
                    summary = f"Transcribed {result.duration:.1f}s ({result.language}, {provider_model})"
                else:
                    summary = f"Transcribed ({result.language}, {provider_model})"
                self.notify_user.emit("Typely", summary)
            else:
                self.notify_user.emit("Typely", "No speech detected")

            if not emit_result.success:
                self.error_user.emit(emit_result.message)
            else:
                self.notify_user.emit("Typely", emit_result.message)
        except Exception as exc:  # noqa: BLE001
            self.error_user.emit(f"Transcription failed: {exc}")
        finally:
            try:
                if audio_path.exists():
                    os.unlink(audio_path)
            except OSError:
                pass
            with self._state_lock:
                self._transcribing = False
            self._target_window_id = None
            self.tray.set_status("Idle")
            self.control_window.set_status("Idle")
            LOGGER.info("Back to idle state")

    def set_record_mode(self, mode: str) -> None:
        if mode not in {"toggle", "hold", "both"}:
            return
        if not self.hotkeys.update(
            toggle_hotkey=self.config.hotkey_toggle,
            hold_hotkey=self.config.hotkey_hold,
            record_mode=mode,
        ):
            self.error_user.emit("Unable to apply record mode with current hotkeys")
            return
        self.config.record_mode = mode
        self._save_config()
        self.tray.notify("Typely", f"Record mode set to {mode}")

    @staticmethod
    def _normalize_hotkey_value(value: str) -> str:
        return value.strip()

    def _validate_hotkey(self, value: str) -> bool:
        dpy = None
        try:
            dpy = xdisplay.Display()
            parse_hotkey(dpy, value)
            return True
        except Exception as exc:  # noqa: BLE001
            self.error_user.emit(f"Invalid hotkey: {exc}")
            return False
        finally:
            if dpy is not None:
                try:
                    dpy.close()
                except Exception:  # noqa: BLE001
                    pass

    def _update_hotkey_info_label(self) -> None:
        self.control_window.info_label.setText(
            "Hotkeys: Toggle "
            f"{self.config.hotkey_toggle} | Hold {self.config.hotkey_hold}\n"
            "Use tray menu for model/provider/microphone/output settings."
        )

    def set_toggle_hotkey(self, value: str) -> None:
        normalized = self._normalize_hotkey_value(value)
        if not normalized:
            self.error_user.emit("Toggle hotkey cannot be empty")
            return
        if hotkeys_collide(normalized, self.config.hotkey_hold):
            self.error_user.emit("Toggle and hold hotkeys must be different")
            return
        if not self._validate_hotkey(normalized):
            return
        if not self.hotkeys.update(
            toggle_hotkey=normalized,
            hold_hotkey=self.config.hotkey_hold,
            record_mode=self.config.record_mode,
        ):
            self.error_user.emit("Failed to apply toggle hotkey; existing bindings were kept")
            return
        self.config.hotkey_toggle = normalized
        self._update_hotkey_info_label()
        self._save_config()
        self.tray.notify("Typely", f"Toggle hotkey set to {normalized}")

    def set_hold_hotkey(self, value: str) -> None:
        normalized = self._normalize_hotkey_value(value)
        if not normalized:
            self.error_user.emit("Hold hotkey cannot be empty")
            return
        if hotkeys_collide(self.config.hotkey_toggle, normalized):
            self.error_user.emit("Toggle and hold hotkeys must be different")
            return
        if not self._validate_hotkey(normalized):
            return
        if not self.hotkeys.update(
            toggle_hotkey=self.config.hotkey_toggle,
            hold_hotkey=normalized,
            record_mode=self.config.record_mode,
        ):
            self.error_user.emit("Failed to apply hold hotkey; existing bindings were kept")
            return
        self.config.hotkey_hold = normalized
        self._update_hotkey_info_label()
        self._save_config()
        self.tray.notify("Typely", f"Hold hotkey set to {normalized}")

    def reset_hotkeys(self) -> None:
        if not self.hotkeys.update(
            toggle_hotkey=self.DEFAULT_TOGGLE_HOTKEY,
            hold_hotkey=self.DEFAULT_HOLD_HOTKEY,
            record_mode=self.config.record_mode,
        ):
            self.error_user.emit("Failed to reset hotkeys; existing bindings were kept")
            return
        self.config.hotkey_toggle = self.DEFAULT_TOGGLE_HOTKEY
        self.config.hotkey_hold = self.DEFAULT_HOLD_HOTKEY
        self._update_hotkey_info_label()
        self._save_config()
        self.tray.notify("Typely", "Hotkeys reset to defaults")

    def set_default_model(self, model_name: str) -> None:
        if model_name not in MODEL_REGISTRY:
            return
        self.config.default_model = model_name
        self._save_config()
        self.tray.notify("Typely", f"Default model set to {model_name}")

    def set_paste_mode(self, mode: str) -> None:
        if mode not in {"cursor_paste", "clipboard_only"}:
            return
        self.config.paste_mode = mode
        self._save_config()
        self.tray.notify("Typely", f"Output mode set to {mode}")

    def _list_audio_input_devices(self) -> list[tuple[str, str]]:
        try:
            return list_input_devices()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Unable to list audio devices: %s", exc)
            return []

    def refresh_audio_devices(self) -> None:
        devices = self._list_audio_input_devices()
        selected = self.config.audio_device
        known_ids = {device_id for device_id, _ in devices}
        if selected is not None and selected not in known_ids:
            selected = None
            self.config.audio_device = None
            self._save_config()

        self.tray.set_audio_devices(devices=devices, selected_device=selected)

    def set_audio_device(self, device_id: str | None) -> None:
        self.config.audio_device = device_id
        self._save_config()
        label = device_id if device_id is not None else "default"
        self.tray.notify("Typely", f"Microphone set to {label}")

    def set_silence_autostop(self, enabled: bool) -> None:
        self.config.silence_autostop_enabled = enabled
        self._save_config()

    def set_silence_timeout(self, timeout_ms: int) -> None:
        self.config.silence_autostop_ms = int(timeout_ms)
        self.vad.silence_ms = int(timeout_ms)
        self.tray.set_silence_timeout_label(int(timeout_ms))
        self._save_config()

    def set_autostart_enabled(self, enabled: bool) -> None:
        project_root = Path(__file__).resolve().parents[1]
        try:
            if enabled:
                exec_command = build_exec_command(project_root=project_root)
                enable_autostart(exec_command=exec_command, working_dir=project_root)
                self.tray.notify("Typely", "Startup on login enabled")
            else:
                disable_autostart()
                self.tray.notify("Typely", "Startup on login disabled")
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to update startup setting: %s", exc)
            self.tray.notify("Typely Error", f"Failed to update startup setting: {exc}")
        finally:
            self.tray.set_autostart_enabled(is_autostart_enabled())

    def open_model_download_dialog(self) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("Download Whisper Models")
        layout = QVBoxLayout(dialog)

        self._download_labels.clear()
        self._download_buttons.clear()

        for model_name in MODEL_REGISTRY:
            row = QHBoxLayout()
            label = QLabel(self._format_model_status(model_name), dialog)
            button = QPushButton(f"Download {model_name}", dialog)
            button.clicked.connect(lambda checked=False, m=model_name: self._download_model(m))
            row.addWidget(label)
            row.addWidget(button)
            layout.addLayout(row)
            self._download_labels[model_name] = label
            self._download_buttons[model_name] = button

            if self.model_manager.get_status(model_name) == "ready":
                button.setEnabled(False)

        self._download_dialog = dialog
        dialog.exec()
        self._download_dialog = None

    def _download_model(self, model_name: str) -> None:
        button = self._download_buttons.get(model_name)
        if button:
            button.setEnabled(False)

        self.model_manager.download(
            model_name,
            callback=lambda name, status, msg: self.model_update.emit(name, status, msg),
        )

    def _on_model_update(self, model_name: str, status: str, message: str) -> None:
        label = self._download_labels.get(model_name)
        if label:
            label.setText(self._format_model_status(model_name, status_override=status, message_override=message))

        button = self._download_buttons.get(model_name)
        if button and status in {"failed"}:
            button.setEnabled(True)
        if button and status == "ready":
            button.setEnabled(False)

        self.tray.notify("Typely", f"Model {model_name}: {message}")

    def _format_model_status(self, model_name: str, status_override: str | None = None, message_override: str | None = None) -> str:
        status = status_override or self.model_manager.get_status(model_name)
        if message_override:
            return f"{model_name}: {status} ({message_override})"
        return f"{model_name}: {status}"


def run_app(show_window: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    app = QApplication([])
    QApplication.setQuitOnLastWindowClosed(False)

    controller = TypelyController(app)
    controller.start()

    # Show control window if requested (e.g., when launched from app menu)
    if show_window:
        controller.show_control_window()

    app.exec()
