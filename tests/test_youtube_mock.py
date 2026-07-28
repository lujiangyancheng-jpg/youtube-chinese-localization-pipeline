from __future__ import annotations

from unittest.mock import patch

from youtube_localizer.download.youtube import inspect_youtube


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
