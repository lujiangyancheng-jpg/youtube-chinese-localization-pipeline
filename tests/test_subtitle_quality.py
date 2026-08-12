from __future__ import annotations

from youtube_localizer.models import SubtitleCue
from youtube_localizer.subtitles.quality import audit_subtitles, select_review_cues


def test_quality_audit_reports_fast_duplicate_and_long_lines() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=500, text="one two three four five six seven"),
        SubtitleCue(id=2, start_ms=500, end_ms=1500, text="one two three four five six seven"),
    ]

    report = audit_subtitles(
        cues,
        language="en",
        max_lines=2,
        preferred_line_length=10,
    )

    assert report["flagged_cue_ids"] == [1, 2]
    assert report["findings_by_category"]["reading_speed"] == 2
    assert report["findings_by_category"]["duplicate"] == 1
    assert report["findings_by_category"]["flash"] == 1


def test_quality_audit_uses_chinese_reading_speed() -> None:
    cue = SubtitleCue(id=1, start_ms=0, end_ms=1000, text="你" * 12)

    report = audit_subtitles(
        [cue],
        language="zh",
        max_lines=2,
        preferred_line_length=20,
    )

    assert report["flagged_cue_ids"] == [1]
    assert report["findings_by_category"]["reading_speed"] == 1


def test_quality_review_selection_keeps_only_flagged_timed_cues() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="需要检查。"),
        SubtitleCue(id=2, start_ms=1000, end_ms=2000, text="无需检查。"),
    ]

    review = select_review_cues(cues, {"flagged_cue_ids": [1, "invalid"]})

    assert review == [cues[0]]
