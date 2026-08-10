from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..errors import InputValidationError
from ..models import SourceMetadata
from ..utils.subprocesses import run_command


def _fraction_to_float(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def _display_dimensions(video: dict[str, Any]) -> tuple[int | None, int | None]:
    width = video.get("width")
    height = video.get("height")
    rotations = [video.get("tags", {}).get("rotate")]
    rotations.extend(item.get("rotation") for item in video.get("side_data_list", []))
    for value in rotations:
        try:
            rotated_quarter_turn = round(float(value)) % 180 == 90
        except (TypeError, ValueError):
            continue
        if rotated_quarter_turn:
            return height, width
    return width, height


def probe_media(path: Path, *, ffprobe: str = "ffprobe") -> dict[str, Any]:
    if not path.is_file():
        raise InputValidationError(f"Local video file does not exist: {path}")
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            path,
        ]
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"ffprobe returned invalid JSON for {path}") from exc
    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise InputValidationError(f"No video stream was found in: {path}")
    return data


def metadata_from_probe(path: Path, data: dict[str, Any], *, video_id: str) -> SourceMetadata:
    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    audios = [s for s in data["streams"] if s.get("codec_type") == "audio"]
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    display_width, display_height = _display_dimensions(video)
    average_frame_rate = _fraction_to_float(video.get("avg_frame_rate"))
    stream_frame_rate = _fraction_to_float(video.get("r_frame_rate"))
    return SourceMetadata(
        source_type="local",
        source_input=str(path.resolve()),
        video_id=video_id,
        title=path.stem,
        duration=duration,
        width=display_width,
        height=display_height,
        frame_rate=average_frame_rate or stream_frame_rate,
        video_codec=video.get("codec_name") or "",
        audio_codec=(audios[0].get("codec_name") if audios else "") or "",
        pixel_format=video.get("pix_fmt") or "",
        color_space=video.get("color_space") or "",
        color_transfer=video.get("color_transfer") or "",
        color_primaries=video.get("color_primaries") or "",
        variable_frame_rate=bool(
            average_frame_rate
            and stream_frame_rate
            and abs(average_frame_rate - stream_frame_rate) > 0.01
        ),
        audio_streams=[
            {
                "index": stream.get("index"),
                "codec": stream.get("codec_name"),
                "channels": stream.get("channels"),
                "language": stream.get("tags", {}).get("language", ""),
            }
            for stream in audios
        ],
    )
