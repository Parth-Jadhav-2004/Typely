# Typely

Typely is an Ubuntu Linux tray application for speech-to-text transcription.

## Features

- Tray-first workflow (starts hidden in system tray)
- Global hotkeys for toggle and hold-to-talk recording
- Editable hotkeys from tray menu
- Local Whisper transcription (`small`, `medium`) via `faster-whisper`
- Optional Groq transcription provider
- Model download controls from tray
- Output mode: paste at cursor or clipboard-only
- Silence auto-stop with configurable timeout
- Microphone device selection

## Requirements

- Ubuntu Linux (X11 session for global hotkeys)
- Python 3.11+
- `xclip` and `xdotool` (for clipboard and auto-paste)
- Microphone access

## Setup

```bash
./scripts/setup_ubuntu.sh
```

## Run

```bash
source .venv/bin/activate
python -m typely
```

At launch, Typely stays hidden and runs in the tray. Use `Open Typely` in the tray menu to open the control window.

## Tray Controls

- Start/stop listening
- Open Typely window
- Record mode (`toggle`, `hold`, `both`)
- Hotkeys:
  - Set Toggle Hotkey...
  - Set Hold Hotkey...
  - Reset Hotkeys to Default
- Transcription provider/model settings
- Groq API key/model settings
- Output mode
- Microphone selection and refresh
- Silence auto-stop enable/timeout

## Config

Config file path:

`~/.config/typely/config.json`

Schema keys include:

- `hotkey_toggle`
- `hotkey_hold`
- `record_mode` (`toggle`, `hold`, `both`)
- `default_model` (`small`, `medium`)
- `silence_autostop_enabled`
- `silence_autostop_ms`
- `paste_mode` (`cursor_paste`, `clipboard_only`)
- `audio_device`
- `transcription_provider` (`local`, `groq`)
- `groq_api_key`
- `groq_model`

## Tests

```bash
source .venv/bin/activate
pytest
```
