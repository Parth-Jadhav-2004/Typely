import pytest

from typely.hotkeys import HotkeyState, apply_hotkey_event, hotkeys_collide, mode_allows, parse_hotkey


class _FakeDisplay:
    def keysym_to_keycode(self, keysym: int) -> int:
        return 42 if keysym else 0


def test_mode_allows():
    assert mode_allows("both", "toggle")
    assert mode_allows("both", "hold")
    assert mode_allows("toggle", "toggle")
    assert not mode_allows("toggle", "hold")


def test_toggle_transitions():
    state = HotkeyState()
    state = apply_hotkey_event(state, "toggle", "toggle_press")
    assert state.is_recording
    state = apply_hotkey_event(state, "toggle", "toggle_press")
    assert not state.is_recording


def test_hold_transitions():
    state = HotkeyState()
    state = apply_hotkey_event(state, "hold", "hold_press")
    assert state.is_recording
    assert state.hold_active

    state = apply_hotkey_event(state, "hold", "hold_release")
    assert not state.is_recording
    assert not state.hold_active


def test_parse_hotkey_valid_combo():
    spec = parse_hotkey(_FakeDisplay(), "Ctrl+Shift+Space")
    assert spec.modifiers > 0
    assert spec.keycode == 42
    assert spec.key_label == "Space"


@pytest.mark.parametrize(
    "hotkey,error_message",
    [
        ("Space", "Invalid hotkey string"),
        ("Ctrl+Meta+Space", "Unsupported modifier"),
        ("Ctrl+Shift+NotARealKey", "Unsupported key token"),
    ],
)
def test_parse_hotkey_invalid_formats(hotkey, error_message):
    with pytest.raises(ValueError, match=error_message):
        parse_hotkey(_FakeDisplay(), hotkey)


def test_hotkey_collision_check_is_case_insensitive():
    assert hotkeys_collide("Ctrl+Shift+Space", "ctrl+shift+space")
    assert not hotkeys_collide("Ctrl+Shift+Space", "Ctrl+Alt+Shift+Space")
