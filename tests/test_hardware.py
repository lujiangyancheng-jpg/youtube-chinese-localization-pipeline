from __future__ import annotations

import subprocess
from unittest.mock import patch

from youtube_localizer.errors import ExternalToolError
from youtube_localizer.hardware import (
    H264Encoder,
    SystemResources,
    format_nvidia_gpus,
    probe_h264_nvenc,
    query_nvidia_gpus,
    recommended_cpu_threads,
    resolve_cpu_threads,
    select_h264_encoder,
    select_h264_nvenc_encoder,
)


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
    assert "兼容编码器" in detail
    assert command.call_args.args[0][command.call_args.args[0].index("-c:v") + 1] == "h264_nvenc"
    assert "color=c=black:s=320x240:r=1" in command.call_args.args[0]


def test_nvenc_probe_confirms_a_working_encoder() -> None:
    completed = subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr="")
    with (
        patch("youtube_localizer.hardware.resolve_executable", return_value="ffmpeg"),
        patch("youtube_localizer.hardware.run_command", return_value=completed),
    ):
        ready, detail = probe_h264_nvenc()

    assert ready
    assert "可用" in detail


def test_nvenc_encoder_selects_the_bundled_compatibility_build_when_needed(tmp_path) -> None:
    compatibility = tmp_path / "ffmpeg-compat.exe"
    compatibility.write_bytes(b"")
    with (
        patch(
            "youtube_localizer.hardware.probe_h264_nvenc",
            side_effect=[(False, "默认驱动 API 不够新"), (True, "NVENC 硬件编码可用。")],
        ),
        patch("youtube_localizer.hardware.nvenc_compatibility_ffmpeg", return_value=compatibility),
    ):
        encoder = select_h264_nvenc_encoder("ffmpeg.exe")

    assert encoder.ffmpeg == str(compatibility)
    assert encoder.uses_compatibility_build
    assert "兼容编码器" in encoder.detail


def test_auto_encoder_uses_intel_quick_sync_after_nvenc_is_unavailable() -> None:
    with (
        patch(
            "youtube_localizer.hardware.select_h264_nvenc_encoder",
            return_value=H264Encoder(None, "NVENC unavailable"),
        ),
        patch("youtube_localizer.hardware.resolve_executable", return_value="ffmpeg"),
        patch(
            "youtube_localizer.hardware.probe_h264_encoder",
            side_effect=[(True, "h264_qsv hardware encoding is available")],
        ) as probe,
    ):
        encoder = select_h264_encoder()

    assert encoder.ffmpeg == "ffmpeg"
    assert encoder.codec == "h264_qsv"
    assert probe.call_args.args == ("h264_qsv", "ffmpeg")


def test_cpu_thread_recommendations_preserve_capacity_for_the_desktop() -> None:
    assert recommended_cpu_threads(SystemResources(2, 16 * 1024)) == 1
    assert recommended_cpu_threads(SystemResources(8, 16 * 1024)) == 6
    assert recommended_cpu_threads(SystemResources(16, 32 * 1024)) == 8
    assert recommended_cpu_threads(SystemResources(16, 6 * 1024)) == 2
    assert resolve_cpu_threads(0, SystemResources(8, 16 * 1024)) == 6
    assert resolve_cpu_threads(32, SystemResources(4, 16 * 1024)) == 4
