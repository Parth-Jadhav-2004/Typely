from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Optional

RecordMode = Literal["toggle", "hold", "both"]
ModelName = Literal["small", "medium"]
LanguageMode = Literal["auto"]
PasteMode = Literal["cursor_paste", "clipboard_only"]
TranscriptionProvider = Literal["local", "groq"]

CONFIG_DIR = Path.home() / ".config" / "typely"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class AppConfig:
    hotkey_toggle: str = "Ctrl+Shift+Space"
    hotkey_hold: str = "Ctrl+Alt+Shift+Space"
    record_mode: RecordMode = "both"
    default_model: ModelName = "small"
    language_mode: LanguageMode = "auto"
    silence_autostop_enabled: bool = True
    silence_autostop_ms: int = 1200
    paste_mode: PasteMode = "cursor_paste"
    audio_device: Optional[str] = None
    transcription_provider: TranscriptionProvider = "local"
    groq_api_key: Optional[str] = None
    groq_model: str = "whisper-large-v3-turbo"


def _coerce_config(data: dict[str, Any]) -> AppConfig:
    cfg = AppConfig()
    fields = set(asdict(cfg).keys())
    sanitized = {k: v for k, v in data.items() if k in fields}
    merged = {**asdict(cfg), **sanitized}

    if merged["record_mode"] not in {"toggle", "hold", "both"}:
        merged["record_mode"] = cfg.record_mode
    if merged["default_model"] not in {"small", "medium"}:
        merged["default_model"] = cfg.default_model
    if merged["language_mode"] != "auto":
        merged["language_mode"] = cfg.language_mode
    if merged["paste_mode"] not in {"cursor_paste", "clipboard_only"}:
        merged["paste_mode"] = cfg.paste_mode
    if merged["transcription_provider"] not in {"local", "groq"}:
        merged["transcription_provider"] = cfg.transcription_provider
    if not isinstance(merged["groq_model"], str) or not merged["groq_model"].strip():
        merged["groq_model"] = cfg.groq_model
    if not isinstance(merged["silence_autostop_ms"], int) or merged["silence_autostop_ms"] < 200:
        merged["silence_autostop_ms"] = cfg.silence_autostop_ms

    return AppConfig(**merged)


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()

    if not isinstance(data, dict):
        return AppConfig()

    return _coerce_config(data)


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
