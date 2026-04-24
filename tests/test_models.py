from typely.models import ModelManager


def test_model_status_not_downloaded(tmp_path):
    manager = ModelManager(cache_root=tmp_path)
    assert manager.get_status("small") == "not_downloaded"


def test_model_status_ready_from_safetensors(tmp_path):
    manager = ModelManager(cache_root=tmp_path)
    model_dir = manager.model_path("small")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.safetensors").write_bytes(b"x")

    assert manager.get_status("small") == "ready"
