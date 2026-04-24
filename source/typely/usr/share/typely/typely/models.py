from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Literal, Optional

from huggingface_hub import snapshot_download

ModelStatus = Literal["not_downloaded", "downloading", "ready", "failed"]
DownloadCallback = Callable[[str, ModelStatus, str], None]

MODEL_REGISTRY = {
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}

CACHE_ROOT = Path.home() / ".local" / "share" / "typely" / "models"


@dataclass(slots=True)
class ModelInfo:
    name: str
    repo_id: str
    path: Path
    status: ModelStatus
    message: str = ""


class ModelManager:
    def __init__(self, cache_root: Path = CACHE_ROOT) -> None:
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._status: dict[str, ModelStatus] = {name: self.get_status(name) for name in MODEL_REGISTRY}
        self._status_lock = Lock()

    def model_path(self, model_name: str) -> Path:
        return self.cache_root / model_name

    def get_status(self, model_name: str) -> ModelStatus:
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"Unsupported model: {model_name}")

        path = self.model_path(model_name)
        if path.exists() and any(path.rglob("*.bin")):
            return "ready"
        if path.exists() and any(path.rglob("*.safetensors")):
            return "ready"
        return "not_downloaded"

    def get_model_source(self, model_name: str) -> str:
        local_path = self.model_path(model_name)
        if self.get_status(model_name) == "ready":
            return str(local_path)
        return MODEL_REGISTRY[model_name]

    def list_models(self) -> list[ModelInfo]:
        output: list[ModelInfo] = []
        for name, repo_id in MODEL_REGISTRY.items():
            output.append(
                ModelInfo(
                    name=name,
                    repo_id=repo_id,
                    path=self.model_path(name),
                    status=self.get_status(name),
                )
            )
        return output

    def download(self, model_name: str, callback: Optional[DownloadCallback] = None) -> Thread:
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"Unsupported model: {model_name}")

        thread = Thread(target=self._download_worker, args=(model_name, callback), daemon=True)
        thread.start()
        return thread

    def _set_status(self, model_name: str, status: ModelStatus) -> None:
        with self._status_lock:
            self._status[model_name] = status

    def _emit(self, callback: Optional[DownloadCallback], model_name: str, status: ModelStatus, message: str) -> None:
        self._set_status(model_name, status)
        if callback:
            callback(model_name, status, message)

    def _download_worker(self, model_name: str, callback: Optional[DownloadCallback]) -> None:
        target_dir = self.model_path(model_name)
        if self.get_status(model_name) == "ready":
            self._emit(callback, model_name, "ready", "Model already downloaded")
            return

        self._emit(callback, model_name, "downloading", "Downloading model files...")

        try:
            snapshot_download(
                repo_id=MODEL_REGISTRY[model_name],
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            self._emit(callback, model_name, "ready", "Download completed")
        except Exception as exc:  # noqa: BLE001
            self._emit(callback, model_name, "failed", f"Download failed: {exc}")
