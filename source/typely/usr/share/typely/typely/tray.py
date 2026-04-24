from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMenu, QStyle, QSystemTrayIcon

from typely.config import AppConfig


class TypelyTray:
    def __init__(
        self,
        app: QApplication,
        config: AppConfig,
        on_toggle_listening: Callable[[], None],
        on_record_mode_change: Callable[[str], None],
        on_model_change: Callable[[str], None],
        on_download_models: Callable[[], None],
        on_open_window: Callable[[], None],
        on_set_toggle_hotkey: Callable[[str], None],
        on_set_hold_hotkey: Callable[[str], None],
        on_reset_hotkeys: Callable[[], None],
        on_paste_mode_change: Callable[[str], None],
        on_audio_device_change: Callable[[str | None], None],
        on_refresh_audio_devices: Callable[[], None],
        on_silence_enabled_change: Callable[[bool], None],
        on_silence_timeout_change: Callable[[int], None],
        autostart_enabled: bool,
        on_autostart_change: Callable[[bool], None],
        on_quit: Callable[[], None],
    ) -> None:
        self.app = app
        self.config = config
        self.on_toggle_listening = on_toggle_listening
        self.on_record_mode_change = on_record_mode_change
        self.on_model_change = on_model_change
        self.on_download_models = on_download_models
        self.on_open_window = on_open_window
        self.on_set_toggle_hotkey = on_set_toggle_hotkey
        self.on_set_hold_hotkey = on_set_hold_hotkey
        self.on_reset_hotkeys = on_reset_hotkeys
        self.on_paste_mode_change = on_paste_mode_change
        self.on_audio_device_change = on_audio_device_change
        self.on_refresh_audio_devices = on_refresh_audio_devices
        self.on_silence_enabled_change = on_silence_enabled_change
        self.on_silence_timeout_change = on_silence_timeout_change
        self.on_autostart_change = on_autostart_change
        self.on_quit = on_quit

        self.tray = QSystemTrayIcon(self._build_icon(), app)
        self.menu = QMenu()

        self.status_action = QAction("Status: Idle", self.menu)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.listen_action = QAction("Start Listening", self.menu)
        self.listen_action.triggered.connect(self.on_toggle_listening)
        self.menu.addAction(self.listen_action)

        self.open_action = QAction("Open Typely", self.menu)
        self.open_action.triggered.connect(self.on_open_window)
        self.menu.addAction(self.open_action)

        self.menu.addSeparator()
        self._build_record_mode_menu()
        self._build_hotkeys_menu()
        self._build_model_menu()

        self.download_action = QAction("Download Models...", self.menu)
        self.download_action.triggered.connect(self.on_download_models)
        self.menu.addAction(self.download_action)

        self.menu.addSeparator()
        self._build_paste_mode_menu()
        self._build_audio_menu()

        self.silence_enabled_action = QAction("Enable Silence Auto-stop", self.menu)
        self.silence_enabled_action.setCheckable(True)
        self.silence_enabled_action.setChecked(self.config.silence_autostop_enabled)
        self.silence_enabled_action.toggled.connect(self.on_silence_enabled_change)
        self.menu.addAction(self.silence_enabled_action)

        self.silence_timeout_action = QAction(
            f"Set Silence Timeout ({self.config.silence_autostop_ms} ms)",
            self.menu,
        )
        self.silence_timeout_action.triggered.connect(self._prompt_silence_timeout)
        self.menu.addAction(self.silence_timeout_action)

        self.autostart_action = QAction("Start Typely on Login", self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(autostart_enabled)
        self.autostart_action.toggled.connect(self.on_autostart_change)
        self.menu.addAction(self.autostart_action)

        self.menu.addSeparator()
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.on_quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("Typely")
        self.tray.show()

    def _build_icon(self) -> QIcon:
        return self.app.style().standardIcon(QStyle.SP_MediaVolume)

    def _build_record_mode_menu(self) -> None:
        submenu = self.menu.addMenu("Record Mode")
        group = QActionGroup(submenu)
        group.setExclusive(True)

        self.record_mode_actions: dict[str, QAction] = {}
        for key, label in (("toggle", "Toggle"), ("hold", "Hold to Talk"), ("both", "Both")):
            action = QAction(label, submenu)
            action.setCheckable(True)
            action.setChecked(self.config.record_mode == key)
            action.triggered.connect(lambda checked, m=key: checked and self.on_record_mode_change(m))
            group.addAction(action)
            submenu.addAction(action)
            self.record_mode_actions[key] = action

    def _build_model_menu(self) -> None:
        submenu = self.menu.addMenu("Model")
        group = QActionGroup(submenu)
        group.setExclusive(True)

        self.model_actions: dict[str, QAction] = {}
        for key, label in (("small", "Small"), ("medium", "Medium")):
            action = QAction(label, submenu)
            action.setCheckable(True)
            action.setChecked(self.config.default_model == key)
            action.triggered.connect(lambda checked, m=key: checked and self.on_model_change(m))
            group.addAction(action)
            submenu.addAction(action)
            self.model_actions[key] = action

    def _build_hotkeys_menu(self) -> None:
        submenu = self.menu.addMenu("Hotkeys")

        set_toggle_action = QAction("Set Toggle Hotkey...", submenu)
        set_toggle_action.triggered.connect(self._prompt_toggle_hotkey)
        submenu.addAction(set_toggle_action)

        set_hold_action = QAction("Set Hold Hotkey...", submenu)
        set_hold_action.triggered.connect(self._prompt_hold_hotkey)
        submenu.addAction(set_hold_action)

        submenu.addSeparator()

        reset_action = QAction("Reset Hotkeys to Default", submenu)
        reset_action.triggered.connect(self.on_reset_hotkeys)
        submenu.addAction(reset_action)

    def _prompt_toggle_hotkey(self) -> None:
        value, accepted = QInputDialog.getText(
            None,
            "Toggle Hotkey",
            "Enter toggle hotkey (example: Ctrl+Shift+Space):",
            QLineEdit.EchoMode.Normal,
            self.config.hotkey_toggle,
        )
        if accepted:
            self.on_set_toggle_hotkey(value)

    def _prompt_hold_hotkey(self) -> None:
        value, accepted = QInputDialog.getText(
            None,
            "Hold Hotkey",
            "Enter hold hotkey (example: Ctrl+Alt+Shift+Space):",
            QLineEdit.EchoMode.Normal,
            self.config.hotkey_hold,
        )
        if accepted:
            self.on_set_hold_hotkey(value)

    def _build_paste_mode_menu(self) -> None:
        submenu = self.menu.addMenu("Output Mode")
        group = QActionGroup(submenu)
        group.setExclusive(True)

        self.paste_mode_actions: dict[str, QAction] = {}
        for key, label in (("cursor_paste", "Paste at Cursor"), ("clipboard_only", "Clipboard Only")):
            action = QAction(label, submenu)
            action.setCheckable(True)
            action.setChecked(self.config.paste_mode == key)
            action.triggered.connect(lambda checked, m=key: checked and self.on_paste_mode_change(m))
            group.addAction(action)
            submenu.addAction(action)
            self.paste_mode_actions[key] = action

    def _build_audio_menu(self) -> None:
        self.audio_submenu = self.menu.addMenu("Microphone")
        self.audio_refresh_action = QAction("Refresh Devices", self.audio_submenu)
        self.audio_refresh_action.triggered.connect(self.on_refresh_audio_devices)
        self.audio_submenu.addAction(self.audio_refresh_action)
        self.audio_submenu.addSeparator()

        self.audio_group = QActionGroup(self.audio_submenu)
        self.audio_group.setExclusive(True)
        self.audio_device_actions: dict[str, QAction] = {}

    def set_audio_devices(self, devices: list[tuple[str, str]], selected_device: str | None) -> None:
        for action in list(self.audio_device_actions.values()):
            self.audio_group.removeAction(action)
            self.audio_submenu.removeAction(action)

        self.audio_device_actions.clear()

        entries = [("", "Default Device")] + devices
        selected = selected_device or ""

        for key, label in entries:
            action = QAction(label, self.audio_submenu)
            action.setCheckable(True)
            action.setChecked(key == selected)
            action.triggered.connect(
                lambda checked, value=key: checked and self.on_audio_device_change(value or None)
            )
            self.audio_group.addAction(action)
            self.audio_submenu.addAction(action)
            self.audio_device_actions[key] = action

    def _prompt_silence_timeout(self) -> None:
        value, accepted = QInputDialog.getInt(
            None,
            "Silence Timeout",
            "Auto-stop after silence (milliseconds):",
            value=self.config.silence_autostop_ms,
            minValue=200,
            maxValue=10000,
            step=100,
        )
        if accepted:
            self.on_silence_timeout_change(int(value))

    def set_listening(self, listening: bool) -> None:
        self.listen_action.setText("Stop Listening" if listening else "Start Listening")
        self.status_action.setText("Status: Listening" if listening else "Status: Idle")

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.status_action.setText("Status: Transcribing")

    def set_status(self, text: str) -> None:
        self.status_action.setText(f"Status: {text}")

    def set_silence_timeout_label(self, value_ms: int) -> None:
        self.silence_timeout_action.setText(f"Set Silence Timeout ({value_ms} ms)")

    def set_autostart_enabled(self, enabled: bool) -> None:
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(enabled)
        self.autostart_action.blockSignals(False)

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 2500)

    def close(self) -> None:
        self.tray.hide()

    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()
