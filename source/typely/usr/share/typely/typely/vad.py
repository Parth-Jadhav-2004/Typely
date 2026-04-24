from __future__ import annotations

import time

import webrtcvad


class SilenceDetector:
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        silence_ms: int = 1200,
        aggressiveness: int = 2,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.silence_ms = silence_ms
        self.vad = webrtcvad.Vad(aggressiveness)
        self._last_speech_at = time.monotonic()

    @property
    def frame_bytes(self) -> int:
        samples_per_frame = int(self.sample_rate * self.frame_ms / 1000)
        return samples_per_frame * 2

    def reset(self) -> None:
        self._last_speech_at = time.monotonic()

    def feed(self, pcm_bytes: bytes) -> bool:
        if len(pcm_bytes) != self.frame_bytes:
            return False
        is_speech = self.vad.is_speech(pcm_bytes, self.sample_rate)
        if is_speech:
            self._last_speech_at = time.monotonic()
        return is_speech

    def should_stop(self, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        return (current - self._last_speech_at) * 1000 >= self.silence_ms
