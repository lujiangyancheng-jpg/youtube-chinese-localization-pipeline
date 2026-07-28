from __future__ import annotations

from pathlib import Path

from ..utils.subprocesses import run_command


def build_audio_extract_command(
    source_video: Path,
    output_wav: Path,
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
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]


def extract_transcription_audio(
    source_video: Path,
    output_wav: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> Path:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    temp = output_wav.with_name(f"{output_wav.stem}.partial{output_wav.suffix}")
    run_command(build_audio_extract_command(source_video, temp, ffmpeg=ffmpeg))
    temp.replace(output_wav)
    return output_wav
