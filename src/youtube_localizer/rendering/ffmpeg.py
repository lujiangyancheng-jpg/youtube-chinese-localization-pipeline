from __future__ import annotations

import logging
from pathlib import Path

from ..config import RenderConfig
from ..errors import ExternalToolError, LocalizerError
from ..utils.subprocesses import run_command

LOGGER = logging.getLogger(__name__)


def escape_filter_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'").replace("[", r"\[").replace("]", r"\]")
    return value


def build_hardsub_command(
    source_video: Path,
    subtitle_file: Path,
    output_file: Path,
    config: RenderConfig,
    *,
    source_audio_codec: str = "",
    ffmpeg: str = "ffmpeg",
    start: float | None = None,
    duration: float | None = None,
) -> list[str]:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        command += ["-ss", str(max(0, start))]
    command += ["-i", str(source_video)]
    if duration is not None:
        command += ["-t", str(max(0.1, duration))]
    escaped = escape_filter_path(subtitle_file)
    filter_name = "ass" if subtitle_file.suffix.lower() in {".ass", ".ssa"} else "subtitles"
    command += [
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        f"{filter_name}=filename='{escaped}'",
        "-c:v",
        config.codec,
    ]
    if config.codec in {"libx264", "libx265"}:
        command += ["-crf", str(config.crf), "-preset", config.preset]
    elif config.codec in {"h264_nvenc", "hevc_nvenc"}:
        command += ["-cq", str(config.crf), "-preset", config.preset]
    if config.copy_audio_when_possible and source_audio_codec.lower() == "aac":
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", config.audio_codec, "-b:a", config.audio_bitrate]
    if config.faststart:
        command += ["-movflags", "+faststart"]
    command += [str(output_file)]
    return command


def render_hardsub(
    source_video: Path,
    subtitle_file: Path,
    output_file: Path,
    config: RenderConfig,
    *,
    source_audio_codec: str = "",
    ffmpeg: str = "ffmpeg",
    start: float | None = None,
    duration: float | None = None,
) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp = output_file.with_name(f"{output_file.stem}.partial{output_file.suffix}")
    command = build_hardsub_command(
        source_video,
        subtitle_file,
        temp,
        config,
        source_audio_codec=source_audio_codec,
        ffmpeg=ffmpeg,
        start=start,
        duration=duration,
    )
    try:
        run_command(command)
    except ExternalToolError as exc:
        if config.codec in {"h264_nvenc", "hevc_nvenc"}:
            LOGGER.warning("Hardware encoding failed; retrying with libx264.")
            fallback = config.model_copy(update={"codec": "libx264", "preset": "medium"})
            run_command(
                build_hardsub_command(
                    source_video,
                    subtitle_file,
                    temp,
                    fallback,
                    source_audio_codec=source_audio_codec,
                    ffmpeg=ffmpeg,
                    start=start,
                    duration=duration,
                )
            )
        else:
            hint = ""
            if "No such filter" in str(exc) or "subtitles" in str(exc).lower():
                hint = " Ensure your FFmpeg build includes libass subtitle support."
            raise LocalizerError(f"FFmpeg hard-subtitle rendering failed.{hint}\n{exc}") from exc
    if not temp.is_file() or temp.stat().st_size == 0:
        raise LocalizerError("FFmpeg reported success but did not create a rendered video.")
    temp.replace(output_file)
    return output_file


def build_softsub_command(
    source_video: Path,
    subtitle_file: Path,
    output_file: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(subtitle_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "1:0",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=zho",
        "-movflags",
        "+faststart",
        str(output_file),
    ]
