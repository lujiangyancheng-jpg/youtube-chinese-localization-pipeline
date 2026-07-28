from __future__ import annotations

from youtube_localizer.download.youtube import (
    choose_english_subtitle,
    is_youtube_url,
    youtube_video_id,
)


def test_youtube_url_recognition() -> None:
    assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")
    assert not is_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")
    assert not is_youtube_url("not a url")


def test_youtube_video_id_variants() -> None:
    expected = "dQw4w9WgXcQ"
    assert youtube_video_id(f"https://www.youtube.com/watch?v={expected}&t=2") == expected
    assert youtube_video_id(f"https://youtu.be/{expected}") == expected
    assert youtube_video_id(f"https://www.youtube.com/shorts/{expected}") == expected


def test_creator_english_subtitle_has_priority() -> None:
    info = {
        "subtitles": {"en-GB": [{}]},
        "automatic_captions": {"en": [{}]},
    }
    assert choose_english_subtitle(info) == ("en-GB", "creator")
