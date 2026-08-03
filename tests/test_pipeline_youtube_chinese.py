from __future__ import annotations

from unittest.mock import patch

from youtube_localizer.config import AppConfig
from youtube_localizer.download.youtube import YouTubeDownloadResult
from youtube_localizer.models import ProjectPaths, SourceMetadata
from youtube_localizer.pipeline import process_pipeline
from youtube_localizer.subtitles.parser import parse_subtitle


def test_pipeline_uses_youtube_chinese_without_english_or_translation(tmp_path) -> None:
    project = ProjectPaths(tmp_path / "project")
    project.create()
    url = "https://youtu.be/dQw4w9WgXcQ"
    metadata = SourceMetadata(
        source_type="youtube",
        source_input=url,
        source_url=url,
        video_id="dQw4w9WgXcQ",
        title="Provided Chinese test",
        duration=2.0,
        audio_codec="aac",
    )
    raw_info = {"id": metadata.video_id, "title": metadata.title}

    def fake_download(*_args, **_kwargs):
        video = project.source / "source_video.mp4"
        video.write_bytes(b"synthetic video")
        subtitle = project.source / "source.zh.vtt"
        subtitle.write_text(
            "WEBVTT\n\n00:00:00.100 --> 00:00:01.900\nYouTube提供的中文字幕\n",
            encoding="utf-8",
        )
        return YouTubeDownloadResult(
            video=video,
            chinese_subtitle=subtitle,
            chinese_language="zh-Hans",
            chinese_kind="creator",
        )

    def fake_render(active_project, _config):
        output = active_project.rendered / "chinese_hardsub.mp4"
        output.write_bytes(b"rendered")
        return output

    config = AppConfig.model_validate(
        {
            "download": {"prefer_youtube_chinese": True},
            "translation": {"provider": "manual"},
            "publishing": {"generate_metadata": False},
        }
    )
    with (
        patch(
            "youtube_localizer.pipeline.prepare_project",
            return_value=(project, metadata, raw_info),
        ),
        patch("youtube_localizer.pipeline.download_youtube", side_effect=fake_download),
        patch("youtube_localizer.pipeline.render_project", side_effect=fake_render),
    ):
        result = process_pipeline(url, config)

    assert result.status == "completed"
    assert not project.english_srt.exists()
    assert parse_subtitle(project.chinese_srt)[0].text == "YouTube提供的中文字幕"
    assert (project.rendered / "chinese_hardsub.mp4").is_file()
