from __future__ import annotations

import pytest

from youtube_localizer.models import SubtitleCue
from youtube_localizer.subtitles.bilingual import align_bilingual_tracks, combine_bilingual
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


def test_youtube_word_timestamps_placeholders_and_rolling_flashes_are_removed() -> None:
    content = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.350 align:start position:0%
{space}
Chelsea<00:00:00.840><c> are</c><00:00:01.080><c> once</c><00:00:01.440><c> again</c>

00:00:02.350 --> 00:00:02.360 align:start position:0%
Chelsea are once again

00:00:02.360 --> 00:00:04.110 align:start position:0%
Chelsea are once again
busy<00:00:02.760><c> in</c><00:00:03.200><c> London</c>

00:00:04.110 --> 00:00:04.120 align:start position:0%
busy in London

00:00:04.120 --> 00:00:04.130 align:start position:0%
{space}
{space}

00:00:04.130 --> 00:00:06.000 align:start position:0%
The next sentence
""".replace("{space}", " ")

    normalized = normalize_cues(parse_vtt_text(content))

    assert [(cue.start_ms, cue.end_ms, cue.text) for cue in normalized] == [
        (0, 2350, "Chelsea are once again"),
        (2360, 4110, "busy in London"),
        (4130, 6000, "The next sentence"),
    ]
    assert all("<" not in cue.text and cue.end_ms - cue.start_ms > 1000 for cue in normalized)


def test_vtt_cue_identifiers_do_not_leak_into_previous_text() -> None:
    content = """WEBVTT

first-cue
00:00:00.000 --> 00:00:01.000
Hello

second-cue
00:00:01.000 --> 00:00:02.000
World
"""

    cues = parse_vtt_text(content)

    assert [cue.text for cue in cues] == ["Hello", "World"]


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


def test_independent_language_tracks_align_to_chinese_target_timeline() -> None:
    english = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="Hello"),
        SubtitleCue(id=2, start_ms=1000, end_ms=2000, text="world"),
    ]
    chinese = [SubtitleCue(id=1, start_ms=0, end_ms=2000, text="你好世界")]

    aligned_english, aligned_chinese = align_bilingual_tracks(
        english,
        chinese,
        reference_language="zh",
    )
    bilingual = combine_bilingual(
        aligned_english,
        aligned_chinese,
        mode="bilingual_en_zh",
    )

    assert len(bilingual) == 1
    assert bilingual[0].start_ms == 0
    assert bilingual[0].end_ms == 2000
    assert bilingual[0].text == "Hello world\n你好世界"
