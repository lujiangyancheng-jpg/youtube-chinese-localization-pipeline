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


def test_pipeline_aligns_independent_youtube_tracks_and_preserves_warnings_on_resume(
    tmp_path,
) -> None:
    project = ProjectPaths(tmp_path / "project")
    project.create()
    url = "https://youtu.be/dQw4w9WgXcQ"
    metadata = SourceMetadata(
        source_type="youtube",
        source_input=url,
        source_url=url,
        video_id="dQw4w9WgXcQ",
        title="Independent bilingual tracks",
        duration=2.0,
        width=1920,
        height=1080,
        audio_codec="aac",
    )
    calls = 0

    def fake_download(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        video = project.source / "source_video.mp4"
        video.write_bytes(b"synthetic video")
        english = project.source / "source.en.vtt"
        english.write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n\n"
            "00:00:01.000 --> 00:00:02.000\nworld\n",
            encoding="utf-8",
        )
        chinese = project.source / "source.zh.vtt"
        chinese.write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n你好世界\n",
            encoding="utf-8",
        )
        return YouTubeDownloadResult(
            video=video,
            english_subtitle=english,
            english_language="en",
            english_kind="creator",
            chinese_subtitle=chinese,
            chinese_language="zh-Hans",
            chinese_kind="creator",
            warnings=("subtitle HTTP 429 fallback",),
        )

    def fake_render(active_project, _config):
        active_project.chinese_hardsub.write_bytes(b"rendered")
        return active_project.chinese_hardsub

    config = AppConfig.model_validate(
        {
            "subtitle_mode": "bilingual_en_zh",
            "download": {"prefer_youtube_chinese": True},
            "translation": {"provider": "manual"},
            "publishing": {"generate_metadata": False},
        }
    )
    with (
        patch(
            "youtube_localizer.pipeline.prepare_project",
            return_value=(project, metadata, {"id": metadata.video_id}),
        ),
        patch("youtube_localizer.pipeline.download_youtube", side_effect=fake_download),
        patch("youtube_localizer.pipeline.render_project", side_effect=fake_render),
        patch("youtube_localizer.pipeline.configure_logging"),
    ):
        first = process_pipeline(url, config)
        second = process_pipeline(url, config, resume=True)

    bilingual = parse_subtitle(project.bilingual_srt)
    assert calls == 1
    assert bilingual[0].text == "Hello world\n你好世界"
    assert first.warnings == ["subtitle HTTP 429 fallback"]
    assert second.warnings == first.warnings
