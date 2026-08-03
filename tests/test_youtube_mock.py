from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from youtube_localizer.config import DownloadConfig
from youtube_localizer.download.youtube import download_youtube, inspect_youtube


class FakeYDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def extract_info(self, url, download=False):
        return {
            "id": "dQw4w9WgXcQ",
            "title": "Owned demo",
            "channel": "Creator",
            "duration": 12.5,
            "availability": "public",
            "webpage_url": url,
        }


def test_youtube_inspection_uses_metadata_without_downloading() -> None:
    with patch("youtube_localizer.download.youtube._youtube_dl", side_effect=FakeYDL):
        metadata, raw = inspect_youtube("https://youtu.be/dQw4w9WgXcQ")
    assert metadata.title == "Owned demo"
    assert metadata.channel == "Creator"
    assert raw["id"] == "dQw4w9WgXcQ"


class FakeDownloadYDL:
    last_options = None

    def __init__(self, options):
        self.options = options
        FakeDownloadYDL.last_options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def extract_info(self, url, download=True):
        destination = Path(self.options["outtmpl"]).parent
        (destination / "download.mp4").write_bytes(b"video")
        for language in self.options["subtitleslangs"]:
            (destination / f"download.{language}.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nText\n",
                encoding="utf-8",
            )
        return {"id": "dQw4w9WgXcQ", "ext": "mp4", "webpage_url": url}

    def prepare_filename(self, info):
        return str(Path(self.options["outtmpl"]).parent / "download.mp4")


def test_download_gets_english_and_provided_chinese_subtitles(tmp_path) -> None:
    info = {
        "subtitles": {"en": [{}]},
        "automatic_captions": {"zh-Hans": [{}]},
    }
    with patch("youtube_localizer.download.youtube._youtube_dl", side_effect=FakeDownloadYDL):
        result = download_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            info,
            tmp_path,
            DownloadConfig(prefer_youtube_chinese=True),
        )

    assert result.video.name == "source_video.mp4"
    assert result.english_subtitle == tmp_path / "source.en.vtt"
    assert result.chinese_subtitle == tmp_path / "source.zh.vtt"
    assert result.chinese_language == "zh-Hans"
    assert result.chinese_kind == "automatic"
    assert FakeDownloadYDL.last_options["writesubtitles"] is True
    assert FakeDownloadYDL.last_options["writeautomaticsub"] is True
