from __future__ import annotations

import pytest

from youtube_localizer.models import SubtitleCue
from youtube_localizer.subtitles.normalize import (
    normalize_cues,
    remove_rolling_overlap,
    validate_cues,
)
from youtube_localizer.subtitles.parser import (
    parse_srt_text,
    parse_vtt_text,
    serialize_srt,
)


def test_parse_and_serialize_srt() -> None:
    content = (
        "9\n00:00:01,000 --> 00:00:02,500\nHello world\n\n"
        "12\n00:00:03,000 --> 00:00:04,000\nNext line\n"
    )
    cues = parse_srt_text(content)
    assert [cue.id for cue in cues] == [1, 2]
    assert cues[0].start_ms == 1000
    assert "1\n00:00:01,000 --> 00:00:02,500\nHello world" in serialize_srt(cues)


def test_vtt_to_srt_conversion_ignores_settings_and_decodes_entities() -> None:
    content = """WEBVTT

00:00:00.000 --> 00:00:01.500 align:start position:0%
<c>Hello &amp; welcome</c>
"""
    normalized = normalize_cues(parse_vtt_text(content))
    assert normalized[0].text == "Hello & welcome"
    assert "-->" in serialize_srt(normalized)


def test_rolling_caption_deduplication() -> None:
    assert remove_rolling_overlap("we are building", "we are building a tool") == "a tool"
    assert remove_rolling_overlap("this is a test", "a test today") == "today"
    assert remove_rolling_overlap("same", "same") == ""


def test_normalize_preserves_sound_descriptions() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="♪ [Music] ♪"),
        SubtitleCue(id=2, start_ms=1000, end_ms=2000, text="<c>Hello</c>"),
    ]
    normalized = normalize_cues(cues)
    assert normalized[0].text == "[Music]"
    assert normalized[1].text == "Hello"


def test_validate_cues_reports_timing_and_duplicate_errors() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="same"),
        SubtitleCue(id=3, start_ms=900, end_ms=1200, text="same"),
    ]
    errors = validate_cues(cues)
    assert any("non-sequential" in error for error in errors)
    assert any("duplicates" in error for error in errors)


def test_parser_rejects_empty_file() -> None:
    with pytest.raises(Exception, match="No valid"):
        parse_srt_text("")
