from __future__ import annotations

from pathlib import Path

from ..config import RenderConfig
from .ffmpeg import render_hardsub


def render_preview(
    source_video: Path,
    subtitle_file: Path,
    output_file: Path,
    config: RenderConfig,
    *,
    source_audio_codec: str = "",
    start: float = 0,
    duration: float = 15,
) -> Path:
    return render_hardsub(
        source_video,
        subtitle_file,
        output_file,
        config,
        source_audio_codec=source_audio_codec,
        start=start,
        duration=duration,
    )
