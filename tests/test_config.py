import json

from typely.config import AppConfig, load_config, save_config


def test_load_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg == AppConfig()


def test_save_and_reload_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(
        hotkey_toggle="Ctrl+Shift+X",
        hotkey_hold="Ctrl+Alt+Shift+X",
        default_model="medium",
        paste_mode="clipboard_only",
        silence_autostop_ms=1500,
        transcription_provider="groq",
        groq_api_key="test-key",
        groq_model="whisper-large-v3",
    )
    save_config(config, path)

    loaded = load_config(path)
    assert loaded.hotkey_toggle == "Ctrl+Shift+X"
    assert loaded.hotkey_hold == "Ctrl+Alt+Shift+X"
    assert loaded.default_model == "medium"
    assert loaded.paste_mode == "clipboard_only"
    assert loaded.silence_autostop_ms == 1500
    assert loaded.transcription_provider == "groq"
    assert loaded.groq_model == "whisper-large-v3"


def test_invalid_values_fall_back(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "record_mode": "wrong",
                "default_model": "large",
                "paste_mode": "invalid",
                "transcription_provider": "unknown",
                "groq_model": "",
                "silence_autostop_ms": 100,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.record_mode == "both"
    assert loaded.default_model == "small"
    assert loaded.paste_mode == "cursor_paste"
    assert loaded.transcription_provider == "local"
    assert loaded.groq_model == "whisper-large-v3-turbo"
    assert loaded.silence_autostop_ms == 1200
