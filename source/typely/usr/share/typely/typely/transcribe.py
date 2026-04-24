from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

from faster_whisper import WhisperModel

from typely.models import ModelManager


@dataclass(slots=True)
class TranscriptResult:
    text: str
    language: str
    model_name: str
    duration: float


class Transcriber:
    def __init__(self, model_manager: ModelManager, device: str = "cpu", compute_type: str = "int8") -> None:
        self.model_manager = model_manager
        self.device = device
        self.compute_type = compute_type
        self._models: dict[str, WhisperModel] = {}
        self._model_lock = Lock()

    def _load_model(self, model_name: str) -> WhisperModel:
        with self._model_lock:
            if model_name in self._models:
                return self._models[model_name]

            source = self.model_manager.get_model_source(model_name)
            model = WhisperModel(
                source,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.model_manager.cache_root),
            )
            self._models[model_name] = model
            return model

    def transcribe(self, audio_path: Path, model_name: str, language: Optional[str] = None) -> TranscriptResult:
        model = self._load_model(model_name)
        segments, info = model.transcribe(str(audio_path), language=language)

        pieces: list[str] = []
        end_time = 0.0
        for segment in segments:
            segment_text = segment.text.strip()
            if segment_text:
                pieces.append(segment_text)
            end_time = max(end_time, float(segment.end))

        return TranscriptResult(
            text=" ".join(pieces).strip(),
            language=getattr(info, "language", "unknown"),
            model_name=model_name,
            duration=end_time,
        )
