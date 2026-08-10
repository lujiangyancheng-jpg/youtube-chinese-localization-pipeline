from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from youtube_localizer.config import RenderConfig
from youtube_localizer.errors import ExternalToolError
from youtube_localizer.rendering.ffmpeg import build_hardsub_command, build_softsub_command
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


def test_ffmpeg_command_loads_bundled_fonts_directory(tmp_path) -> None:
    source = tmp_path / "source.mp4"
    subtitle = tmp_path / "subtitle.ass"
    output = tmp_path / "output.mp4"
    fonts = tmp_path / "pretty fonts"
    fonts.mkdir()

    command = build_hardsub_command(
        source,
        subtitle,
        output,
        RenderConfig(),
        fonts_directory=fonts,
    )

    subtitle_filter = command[command.index("-vf") + 1]
    assert ":fontsdir='" in subtitle_filter
    assert "pretty fonts" in subtitle_filter


def test_ffmpeg_command_caps_resolution_and_fps_without_upscaling_or_frame_duplication(tmp_path) -> None:
    command = build_hardsub_command(
        tmp_path / "source.mp4",
        tmp_path / "subtitle.ass",
        tmp_path / "output.mp4",
        RenderConfig(output_height=1080, output_fps=60),
        source_frame_rate=120,
    )

    subtitle_filter = command[command.index("-vf") + 1]
    assert "scale=-2:min(1080\\,ih)" in subtitle_filter
    assert "fps=60" in subtitle_filter

    lower_rate_command = build_hardsub_command(
        tmp_path / "source.mp4",
        tmp_path / "subtitle.ass",
        tmp_path / "output.mp4",
        RenderConfig(output_fps=60),
        source_frame_rate=30,
    )
    assert "fps=60" not in lower_rate_command[lower_rate_command.index("-vf") + 1]


def test_softsub_command_stream_copies_media_and_sets_language(tmp_path) -> None:
    command = build_softsub_command(
        tmp_path / "source.mp4",
        tmp_path / "subtitle.srt",
        tmp_path / "output.mp4",
        language="eng",
    )

    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "mov_text"
    assert command[command.index("-metadata:s:s:0") + 1] == "language=eng"


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
