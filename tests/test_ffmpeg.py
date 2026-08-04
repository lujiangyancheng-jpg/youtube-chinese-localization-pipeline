from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from youtube_localizer.config import RenderConfig
from youtube_localizer.errors import ExternalToolError
from youtube_localizer.rendering.ffmpeg import build_hardsub_command
from youtube_localizer.utils.subprocesses import resolve_executable, run_command


def test_ffmpeg_command_is_argument_array_and_escapes_windows_drive(tmp_path) -> None:
    source = tmp_path / "source video.mp4"
    subtitle = tmp_path / "Chinese subtitle.ass"
    output = tmp_path / "out.mp4"
    command = build_hardsub_command(
        source,
        subtitle,
        output,
        RenderConfig(),
        source_audio_codec="aac",
    )
    assert command[0] == "ffmpeg"
    assert "-vf" in command
    assert command[command.index("-progress") + 1] == "pipe:1"
    subtitle_filter = command[command.index("-vf") + 1]
    assert "filename='" in subtitle_filter
    assert "-c:a" in command
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[-1] == str(output)


def test_subprocess_wrapper_never_uses_shell() -> None:
    completed = subprocess.CompletedProcess(["tool"], 0, stdout="ok", stderr="")
    with patch(
        "youtube_localizer.utils.subprocesses.subprocess.run", return_value=completed
    ) as run:
        result = run_command(["tool", "--version"])
    assert result.stdout == "ok"
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["check"] is False


def test_subprocess_wrapper_explains_windows_control_c_exit() -> None:
    completed = subprocess.CompletedProcess(
        ["ffmpeg"], 3221225786, stdout="", stderr=""
    )
    with (
        patch(
            "youtube_localizer.utils.subprocesses.subprocess.run",
            return_value=completed,
        ),
        pytest.raises(ExternalToolError, match="interrupted.*0xC000013A"),
    ):
        run_command(["ffmpeg", "-version"])


def test_resolve_executable_detects_winget_ffmpeg(tmp_path, monkeypatch) -> None:
    if os.name != "nt":
        return
    ffmpeg = (
        tmp_path
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.1.2-full_build"
        / "bin"
        / "ffmpeg.exe"
    )
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with patch("youtube_localizer.utils.subprocesses.shutil.which", return_value=None):
        assert resolve_executable("ffmpeg") == str(ffmpeg.resolve())
