from __future__ import annotations

from youtube_localizer import media_preview
from youtube_localizer.media_preview import (
    MediaPreview,
    estimate_download_bytes,
    media_preview_summary,
)
from youtube_localizer.models import SourceMetadata


def test_estimate_uses_best_separate_video_and_audio() -> None:
    info = {
        "formats": [
            {"vcodec": "av1", "acodec": "none", "filesize": 800_000_000},
            {"vcodec": "h264", "acodec": "aac", "filesize": 300_000_000},
            {"vcodec": "none", "acodec": "opus", "filesize_approx": 40_000_000},
        ]
    }

    assert estimate_download_bytes(info) == 840_000_000


def test_estimate_falls_back_to_top_level_size() -> None:
    assert estimate_download_bytes({"filesize_approx": 1234}) == 1234
    assert estimate_download_bytes({}) is None


def test_media_preview_summary_contains_the_decision_details() -> None:
    preview = MediaPreview(
        source="video.mp4",
        source_type="local",
        title="Example",
        channel="",
        duration_seconds=3723,
        width=3840,
        height=2160,
        frame_rate=59.94,
        thumbnail_url="",
        estimated_bytes=2_500_000_000,
    )

    summary = media_preview_summary(preview)

    assert "1:02:03" in summary
    assert "3840×2160" in summary
    assert "59.94 FPS" in summary
    assert "GB" in summary


def test_local_preview_uses_file_size_without_downloading(tmp_path, monkeypatch) -> None:
    video = tmp_path / "example.mp4"
    video.write_bytes(b"local-video")
    monkeypatch.setattr(
        media_preview,
        "inspect_local",
        lambda path: SourceMetadata(
            source_type="local",
            source_input=str(path),
            video_id="local",
            title="Local example",
            duration=12.0,
            width=1920,
            height=1080,
            frame_rate=30.0,
        ),
    )

    preview = media_preview.inspect_media_preview(str(video))

    assert preview.title == "Local example"
    assert preview.estimated_bytes == len(b"local-video")


def test_youtube_preview_estimates_the_best_stream_pair(monkeypatch) -> None:
    monkeypatch.setattr(media_preview, "is_youtube_url", lambda _value: True)
    monkeypatch.setattr(
        media_preview,
        "inspect_youtube",
        lambda value: (
            SourceMetadata(
                source_type="youtube",
                source_input=value,
                video_id="abc123",
                title="YouTube example",
                duration=90,
            ),
            {
                "formats": [
                    {"vcodec": "av1", "acodec": "none", "filesize": 1000},
                    {"vcodec": "none", "acodec": "opus", "filesize": 200},
                ]
            },
        ),
    )

    preview = media_preview.inspect_media_preview("https://youtu.be/abc123")

    assert preview.title == "YouTube example"
    assert preview.estimated_bytes == 1200
