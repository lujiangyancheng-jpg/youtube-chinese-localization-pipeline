from __future__ import annotations

from pathlib import Path

from ..config import SubtitleConfig
from ..models import SubtitleCue
from ..utils.files import atomic_write_text
from ..utils.text import ms_to_ass


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def write_ass(
    path: Path,
    cues: list[SubtitleCue],
    config: SubtitleConfig,
    *,
    bilingual_mode: str = "chinese",
) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chinese,{config.font},{config.font_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{config.outline},{config.shadow},2,30,30,{config.margin_v},1
Style: English,{config.font},{config.english_font_size},&H00E8E8E8,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{config.outline},{config.shadow},2,30,30,{config.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for cue in cues:
        text = _escape_ass(cue.text)
        if bilingual_mode == "bilingual_en_zh":
            first, _, second = text.partition(r"\N")
            text = rf"{{\rEnglish}}{first}\N{{\rChinese}}{second}"
        elif bilingual_mode == "bilingual_zh_en":
            first, _, second = text.partition(r"\N")
            text = rf"{{\rChinese}}{first}\N{{\rEnglish}}{second}"
        events.append(
            f"Dialogue: 0,{ms_to_ass(cue.start_ms)},{ms_to_ass(cue.end_ms)},Chinese,,0,0,0,,{text}"
        )
    atomic_write_text(path, header + "\n".join(events) + "\n")
