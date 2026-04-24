from pathlib import Path

from typely.autostart import (
    build_exec_command,
    disable_autostart,
    enable_autostart,
    is_autostart_enabled,
    render_desktop_entry,
)


def test_build_exec_command_contains_module_and_workdir(tmp_path):
    command = build_exec_command(project_root=tmp_path, python_executable="/tmp/venv/bin/python")
    assert "/bin/sh -lc" in command
    assert "-m typely" in command
    assert str(tmp_path) in command


def test_render_desktop_entry_has_required_keys(tmp_path):
    content = render_desktop_entry(
        exec_command="/bin/sh -lc 'echo hello'",
        working_dir=tmp_path,
    )
    assert "[Desktop Entry]" in content
    assert "Name=Typely" in content
    assert "Exec=/bin/sh -lc 'echo hello'" in content
    assert f"Path={tmp_path}" in content


def test_enable_disable_autostart_roundtrip(tmp_path):
    path = tmp_path / "typely.desktop"
    enable_autostart(
        exec_command="/bin/sh -lc 'echo hello'",
        working_dir=tmp_path,
        path=path,
    )
    assert is_autostart_enabled(path)

    payload = path.read_text(encoding="utf-8")
    assert "Name=Typely" in payload
    assert "Exec=/bin/sh -lc 'echo hello'" in payload

    disable_autostart(path)
    assert not is_autostart_enabled(path)


def test_disable_autostart_missing_file_noop(tmp_path):
    path = tmp_path / "missing.desktop"
    disable_autostart(path)
    assert not path.exists()
