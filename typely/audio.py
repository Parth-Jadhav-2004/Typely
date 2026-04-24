from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

try:
    import sounddevice as sd
except OSError as exc:  # pragma: no cover - depends on system shared libs
    sd = None
    _SOUNDDEVICE_IMPORT_ERROR = exc
else:
    _SOUNDDEVICE_IMPORT_ERROR = None

FrameCallback = Callable[[bytes], None]


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        frame_ms: int = 30,
        on_frame: Optional[FrameCallback] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms
        self.on_frame = on_frame

        self._buffer = bytearray()
        self._buffer_lock = Lock()
        self._stream: sd.InputStream | None = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self, device: str | int | None = None) -> None:
        if self.running:
            return
        if sd is None:
            raise RuntimeError(
                f"Audio backend unavailable: {_SOUNDDEVICE_IMPORT_ERROR}. "
                "Install PortAudio (libportaudio2 / portaudio19-dev) and retry."
            )

        frame_size = int(self.sample_rate * self.frame_ms / 1000)
        self._buffer = bytearray()

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001, ARG001
            if status:
                return

            chunk = indata.tobytes()
            with self._buffer_lock:
                self._buffer.extend(chunk)

            if self.on_frame:
                self.on_frame(chunk)

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=frame_size,
            callback=callback,
            device=device,
        )
        self._stream.start()

    def stop(self) -> Path:
        if not self.running:
            raise RuntimeError("Recorder is not running")

        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None

        with self._buffer_lock:
            audio_bytes = bytes(self._buffer)

        temp = tempfile.NamedTemporaryFile(prefix="typely_", suffix=".wav", delete=False)
        temp.close()
        wav_path = Path(temp.name)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_bytes)

        return wav_path


def list_input_devices() -> list[tuple[str, str]]:
    if sd is None:
        return []

    devices: list[tuple[str, str]] = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0:
            name = str(info.get("name", f"Device {index}"))
            devices.append((str(index), f"{index}: {name}"))
    return devices
