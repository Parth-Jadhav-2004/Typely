# Typely

Typely is an Ubuntu Linux tray application for speech-to-text transcription.

## Features

- Tray-first workflow (starts hidden in system tray)
- Global hotkeys for toggle and hold-to-talk recording
- Editable hotkeys from tray menu
- Fast, local Whisper transcription (`small`, `medium`) via `faster-whisper`
- Model download controls from tray
- Output mode: paste at cursor or clipboard-only
- Silence auto-stop with configurable timeout
- Microphone device selection
- Easy installation via Debian package

## Requirements

- Ubuntu Linux (X11 session for global hotkeys)
- Python 3.11+
- `xclip` and `xdotool` (for clipboard and auto-paste)
- Microphone access

## Installation

The easiest way to install Typely is using the provided Debian package:

```bash
sudo dpkg -i typely_1.0.0_all.deb
sudo apt-get install -f  # To install any missing dependencies
```

After installation, you can launch Typely directly from your applications menu. The application will start hidden in your system tray.

### Development Setup

If you want to run from source:

```bash
./scripts/setup_ubuntu.sh
source .venv/bin/activate
python -m typely
```

## Tray Controls

- Start/stop listening
- Open Typely window
- Record mode (`toggle`, `hold`, `both`)
- Hotkeys:
  - Set Toggle Hotkey...
  - Set Hold Hotkey...
  - Reset Hotkeys to Default
- Model settings (`small`, `medium`)
- Output mode (`cursor_paste`, `clipboard_only`)
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

## Tests

```bash
source .venv/bin/activate
pytest
```
