from __future__ import annotations

import pytest

from youtube_localizer.config import RenderConfig, SubtitleConfig
from youtube_localizer.download.metadata import probe_media
from youtube_localizer.models import SubtitleCue
from youtube_localizer.rendering.ffmpeg import render_hardsub, render_softsub
from youtube_localizer.rendering.validation import validate_rendered_video
from youtube_localizer.subtitles.parser import write_srt
from youtube_localizer.subtitles.styling import write_ass
from youtube_localizer.utils.subprocesses import resolve_executable, run_command

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not resolve_executable("ffmpeg") or not resolve_executable("ffprobe"),
    reason="local FFmpeg/ffprobe are not installed",
)
def test_offline_synthetic_video_can_be_hardsubbed(tmp_path) -> None:
    source = tmp_path / "synthetic.mp4"
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=2:r=48",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            source,
        ]
    )
    subtitle = tmp_path / "chinese.ass"
    write_ass(
        subtitle,
        [SubtitleCue(id=1, start_ms=100, end_ms=1800, text="本地离线测试")],
        SubtitleConfig(font="Arial", font_size=32),
    )
    ass_content = subtitle.read_text(encoding="utf-8")
    assert "PlayResX: 1920" in ass_content
    assert "PlayResY: 1080" in ass_content
    output = tmp_path / "rendered.mp4"
    render_hardsub(
        source,
        subtitle,
        output,
        RenderConfig(crf=30, preset="ultrafast", output_height=360, output_fps=24),
        source_audio_codec="aac",
    )
    result = validate_rendered_video(output, expected_duration=2)
    assert any(stream.get("codec_type") == "video" for stream in result["streams"])
    rendered_video = next(
        stream for stream in probe_media(output)["streams"] if stream.get("codec_type") == "video"
    )
    assert rendered_video["height"] == 180  # The 180p source was not upscaled to 360p.
    assert rendered_video["avg_frame_rate"] == "24/1"

    softsub_srt = tmp_path / "chinese.srt"
    write_srt(softsub_srt, [SubtitleCue(id=1, start_ms=100, end_ms=1800, text="本地离线测试")])
    softsub = tmp_path / "selectable-subtitle.mp4"
    render_softsub(source, softsub_srt, softsub, language="zho")
    softsub_result = validate_rendered_video(softsub, expected_duration=2)
    assert any(stream.get("codec_type") == "subtitle" for stream in softsub_result["streams"])
