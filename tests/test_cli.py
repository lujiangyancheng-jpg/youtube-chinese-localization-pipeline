from __future__ import annotations

from youtube_localizer.cli import normalize_argv


def test_implicit_process_command() -> None:
    assert normalize_argv(["input.mp4"]) == ["process", "input.mp4"]
    assert normalize_argv(["doctor"]) == ["doctor"]
    assert normalize_argv(["--batch", "inputs.txt"]) == ["batch", "inputs.txt"]
