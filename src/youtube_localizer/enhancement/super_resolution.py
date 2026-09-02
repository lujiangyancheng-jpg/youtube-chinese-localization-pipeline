from __future__ import annotations

import logging
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO

from ..config import EnhancementConfig, RenderConfig
from ..errors import ExternalToolError, LocalizerError
from ..rendering.ffmpeg import resolve_render_backend, video_codec_arguments
from ..resource_gate import heavy_workload_slot
from ..resources import super_resolution_runtime
from ..utils.subprocesses import (
    hidden_console_kwargs,
    resolve_executable,
    run_command,
)

LOGGER = logging.getLogger(__name__)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MODEL_DIRECTORIES = {
    "general": "models-upconv_7_photo",
    "animation": "models-cunet",
}


def super_resolution_target_height(
    source_height: int,
    render: RenderConfig,
    enhancement: EnhancementConfig,
) -> int:
    """Choose a bounded target and never claim more than one 4x AI pass can produce."""
    if enhancement.mode == "off":
        return source_height
    requested = render.output_height
    automatic = min(source_height * enhancement.scale, enhancement.max_auto_height)
    target = requested if requested is not None else automatic
    target = min(target, source_height * 4, 4320)
    return max(source_height, target)


def build_frame_extract_command(source: Path, *, ffmpeg: str = "ffmpeg") -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-fps_mode",
        "passthrough",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]


def build_upscaler_command(
    executable: Path,
    input_directory: Path,
    output_directory: Path,
    model_root: Path,
    enhancement: EnhancementConfig,
    *,
    gpu_id: int | None = None,
) -> list[str]:
    model_directory = model_root / MODEL_DIRECTORIES[enhancement.mode]
    command = [
        str(executable),
        "-i",
        str(input_directory),
        "-o",
        str(output_directory),
        "-n",
        "1",
        "-s",
        str(enhancement.scale),
        "-m",
        str(model_directory),
        "-f",
        "png",
        "-j",
        "1:2:1",
    ]
    if enhancement.tile_size:
        command.extend(["-t", str(enhancement.tile_size)])
    if gpu_id is not None:
        command.extend(["-g", str(gpu_id)])
    return command


def _run_upscaler_batch(
    executable: Path,
    input_directory: Path,
    output_directory: Path,
    model_root: Path,
    enhancement: EnhancementConfig,
    *,
    frame_count: int,
    selected_gpu: int | None,
) -> int:
    """Run one batch and probe alternate Vulkan devices if the preferred GPU crashes."""
    candidates = [selected_gpu] if selected_gpu is not None else [0, 1, 2, 3, -1]
    failures: list[str] = []
    for gpu_id in candidates:
        if output_directory.exists():
            shutil.rmtree(output_directory)
        output_directory.mkdir()
        try:
            run_command(
                build_upscaler_command(
                    executable,
                    input_directory,
                    output_directory,
                    model_root,
                    enhancement,
                    gpu_id=gpu_id,
                ),
                timeout=max(300.0, frame_count * 90.0),
            )
            if selected_gpu is None:
                device = "CPU" if gpu_id == -1 else f"Vulkan GPU {gpu_id}"
                LOGGER.info("AI super resolution selected verified %s.", device)
            return gpu_id
        except ExternalToolError as exc:
            failures.append(f"device {gpu_id}: {exc}")
            if selected_gpu is not None:
                break
            LOGGER.warning("AI upscaler could not use Vulkan device %s; trying fallback.", gpu_id)
    detail = failures[-1] if failures else "no compatible device was reported"
    raise LocalizerError(
        "AI super resolution could not start on any detected GPU or the CPU fallback. "
        f"Last failure: {detail}"
    )


def build_enhanced_encode_command(
    source: Path,
    output: Path,
    *,
    frame_rate: float,
    target_height: int,
    source_audio_codec: str,
    render: RenderConfig,
    ffmpeg: str,
) -> list[str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "image2pipe",
        "-framerate",
        f"{frame_rate:.6f}",
        "-vcodec",
        "png",
        "-i",
        "pipe:0",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-vf",
        f"scale=-2:{target_height}:flags=lanczos",
        "-c:v",
        render.codec,
        *video_codec_arguments(render),
        "-pix_fmt",
        "yuv420p",
    ]
    if render.copy_audio_when_possible and source_audio_codec.casefold() == "aac":
        command.extend(["-c:a", "copy"])
    else:
        command.extend(["-c:a", render.audio_codec, "-b:a", render.audio_bitrate])
    command.extend(["-shortest"])
    if render.faststart:
        command.extend(["-movflags", "+faststart"])
    command.append(str(output))
    return command


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def read_png_frame(stream: BinaryIO) -> bytes | None:
    """Read exactly one PNG from FFmpeg's continuous image2pipe output."""
    signature = _read_exact(stream, len(PNG_SIGNATURE))
    if not signature:
        return None
    if signature != PNG_SIGNATURE:
        raise LocalizerError("FFmpeg returned an invalid PNG frame during AI enhancement.")
    image = bytearray(signature)
    while True:
        header = _read_exact(stream, 8)
        if len(header) != 8:
            raise LocalizerError("FFmpeg ended in the middle of an extracted PNG frame.")
        length, chunk_type = struct.unpack(">I4s", header)
        body = _read_exact(stream, length + 4)
        if len(body) != length + 4:
            raise LocalizerError("FFmpeg returned a truncated PNG frame.")
        image.extend(header)
        image.extend(body)
        if chunk_type == b"IEND":
            return bytes(image)


def _adaptive_batch_frames(
    source_width: int,
    source_height: int,
    target_height: int,
    configured: int,
) -> int:
    if configured:
        return configured
    target_width = max(2, round(source_width * target_height / source_height))
    # Keep decoded/upscaled PNG batches near 320 MiB on ordinary machines.  Four bytes per
    # pixel is conservative enough for the temporary input and output directories together.
    estimate_per_frame = max(1, target_width * target_height * 4)
    return max(4, min(24, (320 * 1024**2) // estimate_per_frame))


def _process_error(stderr_file: BinaryIO, fallback: str) -> str:
    stderr_file.seek(0)
    detail = stderr_file.read().decode("utf-8", errors="replace").strip()[-4000:]
    return detail or fallback


def enhance_video(
    source: Path,
    output: Path,
    *,
    source_width: int,
    source_height: int,
    frame_rate: float,
    duration: float,
    source_audio_codec: str,
    render: RenderConfig,
    enhancement: EnhancementConfig,
    working_directory: Path,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Restore video frames in bounded batches and encode one continuous enhanced MP4."""
    if enhancement.mode == "off":
        raise LocalizerError("AI super resolution is disabled for this project.")
    runtime = super_resolution_runtime()
    if runtime is None:
        raise LocalizerError(
            "AI super-resolution runtime is not installed. Re-run the Standard installer and "
            "select the AI super-resolution pack, or install the matching pack from Releases."
        )
    if source_width <= 0 or source_height <= 0:
        raise LocalizerError("Source dimensions are required for AI super resolution.")
    if frame_rate <= 0:
        raise LocalizerError("Source frame rate is required for AI super resolution.")
    target_height = super_resolution_target_height(source_height, render, enhancement)
    if target_height <= source_height:
        raise LocalizerError(
            "The selected AI target is not larger than the source. Choose a higher output "
            "resolution or turn enhancement off."
        )
    # The bundled 2x/4x NCNN models should do the actual enlargement.  FFmpeg only performs
    # the final small downscale when a requested height sits between those factors.
    active_enhancement = enhancement.model_copy(
        update={"scale": 4 if target_height > source_height * 2 else 2}
    )

    executable, model_root = runtime
    output.parent.mkdir(parents=True, exist_ok=True)
    working_directory.mkdir(parents=True, exist_ok=True)
    batch_root = working_directory / "active-batch"
    if batch_root.exists():
        shutil.rmtree(batch_root)
    input_directory = batch_root / "input"
    output_directory = batch_root / "output"
    input_directory.mkdir(parents=True)
    output_directory.mkdir(parents=True)
    temp_output = output.with_name(f"{output.stem}.partial{output.suffix}")
    temp_output.unlink(missing_ok=True)

    active_ffmpeg, active_render = resolve_render_backend(
        render.model_copy(update={"crf": max(10, render.crf - 3)}),
        ffmpeg,
    )
    extractor_command = build_frame_extract_command(source, ffmpeg=ffmpeg)
    encoder_command = build_enhanced_encode_command(
        source,
        temp_output,
        frame_rate=frame_rate,
        target_height=target_height,
        source_audio_codec=source_audio_codec,
        render=active_render,
        ffmpeg=active_ffmpeg,
    )
    extractor_command[0] = resolve_executable(extractor_command[0]) or extractor_command[0]
    encoder_command[0] = resolve_executable(encoder_command[0]) or encoder_command[0]
    batch_frames = _adaptive_batch_frames(
        source_width,
        source_height,
        target_height,
        enhancement.batch_frames,
    )
    expected_frames = round(duration * frame_rate) if duration > 0 else 0
    LOGGER.info(
        "AI super resolution: %sp -> %sp, %s model, %s-frame bounded batches.",
        source_height,
        target_height,
        enhancement.mode,
        batch_frames,
    )

    extractor: subprocess.Popen[bytes] | None = None
    encoder: subprocess.Popen[bytes] | None = None
    with heavy_workload_slot("AI super resolution", kind="compute"):
        try:
            with tempfile.TemporaryFile() as extractor_stderr, tempfile.TemporaryFile() as encoder_stderr:
                extractor = subprocess.Popen(
                    extractor_command,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=extractor_stderr,
                    **hidden_console_kwargs(),
                )
                encoder = subprocess.Popen(
                    encoder_command,
                    shell=False,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=encoder_stderr,
                    **hidden_console_kwargs(),
                )
                assert extractor.stdout is not None
                assert encoder.stdin is not None
                completed = 0
                selected_gpu: int | None = None
                while True:
                    names: list[str] = []
                    for _ in range(batch_frames):
                        frame = read_png_frame(extractor.stdout)
                        if frame is None:
                            break
                        name = f"frame{completed + len(names) + 1:09d}.png"
                        (input_directory / name).write_bytes(frame)
                        names.append(name)
                    if not names:
                        break
                    selected_gpu = _run_upscaler_batch(
                        executable,
                        input_directory,
                        output_directory,
                        model_root,
                        active_enhancement,
                        frame_count=len(names),
                        selected_gpu=selected_gpu,
                    )
                    for name in names:
                        enhanced = output_directory / name
                        if not enhanced.is_file():
                            raise LocalizerError(
                                f"The AI upscaler did not create the expected enhanced frame: {name}"
                            )
                        encoder.stdin.write(enhanced.read_bytes())
                    encoder.stdin.flush()
                    completed += len(names)
                    percent = (
                        min(100.0, completed / expected_frames * 100)
                        if expected_frames
                        else 0.0
                    )
                    LOGGER.info(
                        "AI super resolution: %s frames complete%s.",
                        completed,
                        f" ({percent:.1f}%)" if expected_frames else "",
                    )
                    shutil.rmtree(input_directory)
                    shutil.rmtree(output_directory)
                    input_directory.mkdir()
                    output_directory.mkdir()

                encoder.stdin.close()
                extractor_returncode = extractor.wait()
                encoder_returncode = encoder.wait()
                if extractor_returncode != 0:
                    raise ExternalToolError(
                        "FFmpeg frame extraction failed during AI super resolution.\n"
                        + _process_error(extractor_stderr, "No FFmpeg error detail was returned."),
                        command=extractor_command,
                    )
                if encoder_returncode != 0:
                    raise ExternalToolError(
                        "FFmpeg enhanced-video encoding failed.\n"
                        + _process_error(encoder_stderr, "No FFmpeg error detail was returned."),
                        command=encoder_command,
                    )
        except BaseException:
            for process in (extractor, encoder):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
            temp_output.unlink(missing_ok=True)
            raise
        finally:
            if batch_root.exists():
                shutil.rmtree(batch_root)

    if not temp_output.is_file() or temp_output.stat().st_size == 0:
        raise LocalizerError("AI super resolution finished without creating an enhanced video.")
    temp_output.replace(output)
    return output
