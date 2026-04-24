from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from Xlib import X, XK, display

RecordMode = Literal["toggle", "hold", "both"]

LOGGER = logging.getLogger(__name__)

MODIFIER_MAP = {
    "ctrl": X.ControlMask,
    "control": X.ControlMask,
    "alt": X.Mod1Mask,
    "shift": X.ShiftMask,
    "super": X.Mod4Mask,
}

IGNORED_LOCK_MASKS = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]


@dataclass(slots=True)
class HotkeySpec:
    modifiers: int
    keycode: int
    key_label: str


@dataclass(slots=True)
class HotkeyState:
    is_recording: bool = False
    hold_active: bool = False


def mode_allows(mode: RecordMode, kind: str) -> bool:
    if mode == "both":
        return kind in {"toggle", "hold"}
    return mode == kind


def hotkeys_collide(toggle_hotkey: str, hold_hotkey: str) -> bool:
    return toggle_hotkey.casefold() == hold_hotkey.casefold()


def apply_hotkey_event(state: HotkeyState, mode: RecordMode, event: str) -> HotkeyState:
    next_state = HotkeyState(is_recording=state.is_recording, hold_active=state.hold_active)

    if event == "toggle_press" and mode_allows(mode, "toggle"):
        next_state.is_recording = not next_state.is_recording
    elif event == "hold_press" and mode_allows(mode, "hold") and not next_state.hold_active:
        next_state.hold_active = True
        next_state.is_recording = True
    elif event == "hold_release" and mode_allows(mode, "hold") and next_state.hold_active:
        next_state.hold_active = False
        next_state.is_recording = False

    return next_state


def _keysym_for_token(token: str) -> int:
    candidates = [token, token.lower(), token.capitalize()]
    for candidate in candidates:
        keysym = XK.string_to_keysym(candidate)
        if keysym:
            return keysym
    raise ValueError(f"Unsupported key token: {token}")


def parse_hotkey(dpy: display.Display, hotkey: str) -> HotkeySpec:
    parts = [p.strip() for p in hotkey.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"Invalid hotkey string: {hotkey}")

    modifiers = 0
    key_part = parts[-1]

    for modifier_name in parts[:-1]:
        mapped = MODIFIER_MAP.get(modifier_name.lower())
        if mapped is None:
            raise ValueError(f"Unsupported modifier: {modifier_name}")
        modifiers |= mapped

    keysym = _keysym_for_token(key_part)
    keycode = dpy.keysym_to_keycode(keysym)
    if not keycode:
        raise ValueError(f"Unable to map key to keycode: {key_part}")

    return HotkeySpec(modifiers=modifiers, keycode=keycode, key_label=key_part)


class GlobalHotkeyManager:
    def __init__(
        self,
        toggle_hotkey: str,
        hold_hotkey: str,
        record_mode: RecordMode,
        on_toggle_press: Callable[[], None],
        on_hold_press: Callable[[], None],
        on_hold_release: Callable[[], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.toggle_hotkey = toggle_hotkey
        self.hold_hotkey = hold_hotkey
        self.record_mode = record_mode
        self.on_toggle_press = on_toggle_press
        self.on_hold_press = on_hold_press
        self.on_hold_release = on_hold_release
        self.on_error = on_error

        self._dpy: display.Display | None = None
        self._root = None
        self._toggle_spec: HotkeySpec | None = None
        self._hold_spec: HotkeySpec | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._hold_is_pressed = False

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

    def update(self, toggle_hotkey: str, hold_hotkey: str, record_mode: RecordMode) -> bool:
        if self._dpy is None or self._root is None:
            self.toggle_hotkey = toggle_hotkey
            self.hold_hotkey = hold_hotkey
            self.record_mode = record_mode
            return True
        return self._rebind(toggle_hotkey=toggle_hotkey, hold_hotkey=hold_hotkey, record_mode=record_mode)

    def _emit_error(self, message: str) -> None:
        LOGGER.error(message)
        if self.on_error:
            self.on_error(message)

    def _event_loop(self) -> None:
        try:
            self._dpy = display.Display()
            self._root = self._dpy.screen().root
            self._rebind(
                toggle_hotkey=self.toggle_hotkey,
                hold_hotkey=self.hold_hotkey,
                record_mode=self.record_mode,
            )

            while self._running:
                if self._dpy.pending_events():
                    event = self._dpy.next_event()
                    self._handle_event(event)
                else:
                    time.sleep(0.02)
        except Exception as exc:  # noqa: BLE001
            self._emit_error(f"Hotkey manager failed: {exc}")
        finally:
            try:
                if self._root is not None:
                    self._root.ungrab_key(X.AnyKey, X.AnyModifier)
                if self._dpy is not None:
                    self._dpy.flush()
                    self._dpy.close()
            except Exception:  # noqa: BLE001
                pass
            self._dpy = None
            self._root = None

    def _rebind(self, toggle_hotkey: str, hold_hotkey: str, record_mode: RecordMode) -> bool:
        if self._dpy is None or self._root is None:
            return True

        try:
            next_toggle_spec = parse_hotkey(self._dpy, toggle_hotkey)
            next_hold_spec = parse_hotkey(self._dpy, hold_hotkey)
        except ValueError as exc:
            self._emit_error(str(exc))
            return False

        previous_toggle_spec = self._toggle_spec
        previous_hold_spec = self._hold_spec
        previous_mode = self.record_mode

        try:
            self._root.ungrab_key(X.AnyKey, X.AnyModifier)
            if mode_allows(record_mode, "toggle"):
                self._grab(next_toggle_spec)
            if mode_allows(record_mode, "hold"):
                self._grab(next_hold_spec)
            self._dpy.flush()
        except Exception as exc:  # noqa: BLE001
            self._emit_error(f"Failed to register hotkeys: {exc}")
            try:
                self._root.ungrab_key(X.AnyKey, X.AnyModifier)
                if previous_toggle_spec and mode_allows(previous_mode, "toggle"):
                    self._grab(previous_toggle_spec)
                if previous_hold_spec and mode_allows(previous_mode, "hold"):
                    self._grab(previous_hold_spec)
                self._dpy.flush()
            except Exception as rollback_exc:  # noqa: BLE001
                self._emit_error(f"Failed to restore previous hotkeys: {rollback_exc}")
            return False

        self.toggle_hotkey = toggle_hotkey
        self.hold_hotkey = hold_hotkey
        self.record_mode = record_mode
        self._toggle_spec = next_toggle_spec
        self._hold_spec = next_hold_spec
        if not mode_allows(record_mode, "hold"):
            self._hold_is_pressed = False
        return True

    def _grab(self, spec: HotkeySpec) -> None:
        assert self._root is not None
        for lock_mask in IGNORED_LOCK_MASKS:
            self._root.grab_key(
                spec.keycode,
                spec.modifiers | lock_mask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )

    @staticmethod
    def _normalized_mask(state_mask: int) -> int:
        return state_mask & ~(X.LockMask | X.Mod2Mask)

    def _is_match(self, event, spec: HotkeySpec) -> bool:  # noqa: ANN001
        return (
            event.detail == spec.keycode
            and self._normalized_mask(event.state) == self._normalized_mask(spec.modifiers)
        )

    def _handle_event(self, event) -> None:  # noqa: ANN001
        if event.type == X.KeyPress:
            if self._toggle_spec and mode_allows(self.record_mode, "toggle") and self._is_match(event, self._toggle_spec):
                self.on_toggle_press()
                return

            if self._hold_spec and mode_allows(self.record_mode, "hold") and self._is_match(event, self._hold_spec):
                if not self._hold_is_pressed:
                    self._hold_is_pressed = True
                    self.on_hold_press()
                return

        if event.type == X.KeyRelease:
            if self._hold_spec and mode_allows(self.record_mode, "hold") and self._is_match(event, self._hold_spec):
                if self._hold_is_pressed:
                    self._hold_is_pressed = False
                    self.on_hold_release()
