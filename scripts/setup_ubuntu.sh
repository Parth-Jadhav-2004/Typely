#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run as a regular user (not root)."
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-dev \
  portaudio19-dev \
  libportaudio2 \
  ffmpeg \
  xclip \
  xdotool

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt pytest

cat <<EOF

Setup complete.

Next:
1) source .venv/bin/activate
2) python -m typely

EOF
