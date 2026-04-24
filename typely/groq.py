from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

from typely.transcribe import TranscriptResult

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SUPPORTED_GROQ_MODELS = (
    "whisper-large-v3-turbo",
    "whisper-large-v3",
    "distil-whisper-large-v3-en",
)


class GroqTranscriber:
    def __init__(self, api_key: Optional[str], model: str = "whisper-large-v3-turbo", timeout_s: float = 120.0) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.timeout_s = timeout_s

    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> TranscriptResult:
        if not self.api_key:
            raise RuntimeError("Groq API key is not set. Configure it in Typely menu or set GROQ_API_KEY.")

        data: dict[str, str] = {
            "model": self.model,
            "response_format": "json",
        }
        if language:
            data["language"] = language

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "audio/wav")}
            with httpx.Client(timeout=self.timeout_s) as client:
                response = client.post(GROQ_TRANSCRIPTION_URL, headers=headers, data=data, files=files)

        if response.status_code >= 400:
            detail = response.text.strip()
            raise RuntimeError(f"Groq transcription request failed ({response.status_code}): {detail}")

        payload = response.json()
        text = str(payload.get("text", "")).strip()
        language_detected = str(payload.get("language", "unknown"))

        return TranscriptResult(
            text=text,
            language=language_detected,
            model_name=self.model,
            duration=0.0,
        )
