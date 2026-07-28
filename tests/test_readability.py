from __future__ import annotations

from youtube_localizer.models import SubtitleCue
from youtube_localizer.subtitles.readability import readability_pass, wrap_chinese


def test_chinese_line_wrapping_prefers_punctuation() -> None:
    text = "这是一个比较长的中文字幕句子，应该在合适的位置换行显示"
    wrapped = wrap_chinese(text, width=16, max_lines=2)
    assert len(wrapped.splitlines()) == 2
    assert wrapped.splitlines()[0].endswith("，")


def test_reading_speed_warning() -> None:
    cues = [
        SubtitleCue(
            id=1,
            start_ms=0,
            end_ms=1000,
            text="这是一个包含非常多中文字的快速字幕",
        )
    ]
    _, issues = readability_pass(cues, width=20, max_lines=2)
    assert any("characters per second" in issue.message for issue in issues)
