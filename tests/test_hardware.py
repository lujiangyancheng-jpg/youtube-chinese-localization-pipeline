from __future__ import annotations

import subprocess
from unittest.mock import patch

from youtube_localizer.errors import ExternalToolError
from youtube_localizer.hardware import format_nvidia_gpus, probe_h264_nvenc, query_nvidia_gpus


def test_query_nvidia_gpus_parses_driver_and_memory() -> None:
    completed = subprocess.CompletedProcess(
        ["nvidia-smi"],
        0,
        stdout="NVIDIA GeForce RTX 5070, 591.86, 12288, 3210\n",
        stderr="",
    )
    with (
        patch("youtube_localizer.hardware.resolve_executable", return_value="nvidia-smi"),
        patch("youtube_localizer.hardware.run_command", return_value=completed),
    ):
        gpus = query_nvidia_gpus()

    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 5070"
    assert gpus[0].driver_version == "591.86"
    assert gpus[0].total_memory_mib == 12288
    assert "3210/12288 MiB" in format_nvidia_gpus(gpus)


def test_nvenc_probe_reports_a_driver_version_problem_before_rendering() -> None:
    error = ExternalToolError(
        "ffmpeg failed\nThe minimum required Nvidia driver for nvenc is 610.00 or newer"
    )
    with (
        patch("youtube_localizer.hardware.resolve_executable", return_value="ffmpeg"),
        patch("youtube_localizer.hardware.run_command", side_effect=error) as command,
    ):
        ready, detail = probe_h264_nvenc()

    assert not ready
    assert "更新驱动" in detail
    assert command.call_args.args[0][command.call_args.args[0].index("-c:v") + 1] == "h264_nvenc"


def test_nvenc_probe_confirms_a_working_encoder() -> None:
    completed = subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr="")
    with (
        patch("youtube_localizer.hardware.resolve_executable", return_value="ffmpeg"),
        patch("youtube_localizer.hardware.run_command", return_value=completed),
    ):
        ready, detail = probe_h264_nvenc()

    assert ready
    assert "可用" in detail
