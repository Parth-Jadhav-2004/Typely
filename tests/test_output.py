import subprocess

from typely.output import OutputSink


def test_capture_active_window_returns_id(monkeypatch):
    sink = OutputSink()
    sink.has_xdotool = True

    def fake_run(cmd, check, stdout, stderr, text=False, input=None):  # noqa: ANN001, ARG001
        assert cmd == ["xdotool", "getactivewindow"]
        return subprocess.CompletedProcess(cmd, 0, stdout="73400325\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert sink.capture_active_window() == "73400325"


def test_emit_targets_window_for_cursor_paste(monkeypatch):
    sink = OutputSink()
    sink.has_xclip = True
    sink.has_xdotool = True

    calls: list[list[str]] = []

    def fake_run(cmd, check, stdout=None, stderr=None, text=False, input=None):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = sink.emit("hello world", "cursor_paste", target_window_id="73400325")

    assert result.success
    assert result.message == "Pasted transcript at cursor"
    assert calls[0] == ["xclip", "-selection", "clipboard"]
    assert calls[1] == ["xdotool", "windowactivate", "--sync", "73400325"]
    assert calls[2] == ["xdotool", "key", "--clearmodifiers", "--window", "73400325", "ctrl+shift+v"]


def test_emit_clipboard_only(monkeypatch):
    sink = OutputSink()
    sink.has_xclip = True
    sink.has_xdotool = False

    def fake_run(cmd, check, stdout=None, stderr=None, text=False, input=None):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = sink.emit("hello world", "clipboard_only")

    assert result.success
    assert result.message == "Copied transcript to clipboard"
