from __future__ import annotations

from ..errors import SubtitleError
from ..models import SubtitleCue


def combine_bilingual(
    english: list[SubtitleCue],
    chinese: list[SubtitleCue],
    *,
    mode: str,
) -> list[SubtitleCue]:
    if len(english) != len(chinese):
        raise SubtitleError("English and Chinese cue counts differ.")
    combined: list[SubtitleCue] = []
    for en, zh in zip(english, chinese, strict=True):
        if en.id != zh.id or en.start_ms != zh.start_ms or en.end_ms != zh.end_ms:
            raise SubtitleError(f"Bilingual cue {en.id} has mismatched IDs or timestamps.")
        text = f"{en.text}\n{zh.text}" if mode == "bilingual_en_zh" else f"{zh.text}\n{en.text}"
        combined.append(zh.model_copy(update={"text": text}))
    return combined
