from __future__ import annotations

import io
import struct
import zlib

from youtube_localizer.config import EnhancementConfig, RenderConfig
from youtube_localizer.enhancement.super_resolution import (
    _run_upscaler_batch,
    build_enhanced_encode_command,
    build_upscaler_command,
    read_png_frame,
    super_resolution_target_height,
)
from youtube_localizer.errors import ExternalToolError


def _png() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")


def test_target_height_is_bounded_and_never_downscales() -> None:
    enhancement = EnhancementConfig(mode="general")

    assert super_resolution_target_height(720, RenderConfig(), enhancement) == 1440
    assert super_resolution_target_height(
        1080, RenderConfig(output_height=2160), enhancement
    ) == 2160
    assert super_resolution_target_height(
        1080, RenderConfig(output_height=720), enhancement
    ) == 1080
    assert super_resolution_target_height(
        480, RenderConfig(output_height=4320), enhancement
    ) == 1920


def test_upscaler_command_selects_model_scale_and_device(tmp_path) -> None:
    command = build_upscaler_command(
        tmp_path / "waifu2x.exe",
        tmp_path / "input",
        tmp_path / "output",
        tmp_path,
        EnhancementConfig(mode="animation", scale=4, tile_size=128),
        gpu_id=1,
    )

    assert command[command.index("-m") + 1].endswith("models-cunet")
    assert command[command.index("-s") + 1] == "4"
    assert command[command.index("-t") + 1] == "128"
    assert command[command.index("-g") + 1] == "1"


def test_png_reader_splits_a_continuous_pipe() -> None:
    image = _png()
    stream = io.BytesIO(image + image)

    assert read_png_frame(stream) == image
    assert read_png_frame(stream) == image
    assert read_png_frame(stream) is None


def test_upscaler_probes_an_alternate_gpu_after_a_crash(tmp_path, monkeypatch) -> None:
    input_directory = tmp_path / "input"
    output_directory = tmp_path / "output"
    input_directory.mkdir()
    (input_directory / "frame000000001.png").write_bytes(_png())
    attempted: list[int] = []

    def fake_run(command: list[str], **_kwargs) -> None:
        gpu = int(command[command.index("-g") + 1])
        attempted.append(gpu)
        if gpu == 0:
            raise ExternalToolError("driver crash", command=command)
        output_directory.mkdir(exist_ok=True)
        (output_directory / "frame000000001.png").write_bytes(_png())

    monkeypatch.setattr(
        "youtube_localizer.enhancement.super_resolution.run_command", fake_run
    )

    selected = _run_upscaler_batch(
        tmp_path / "waifu2x.exe",
        input_directory,
        output_directory,
        tmp_path,
        EnhancementConfig(mode="general"),
        frame_count=1,
        selected_gpu=None,
    )

    assert selected == 1
    assert attempted == [0, 1]


def test_enhanced_encoder_preserves_optional_audio_and_target_height(tmp_path) -> None:
    command = build_enhanced_encode_command(
        tmp_path / "source.mp4",
        tmp_path / "output.mp4",
        frame_rate=23.976,
        target_height=2160,
        source_audio_codec="aac",
        render=RenderConfig(codec="libx264"),
        ffmpeg="ffmpeg.exe",
    )

    assert "1:a?" in command
    assert "scale=-2:2160:flags=lanczos" in command
    assert command[command.index("-c:a") + 1] == "copy"
