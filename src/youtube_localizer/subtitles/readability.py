from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil

from ..models import SubtitleCue

PUNCTUATION = "，。！？；：、,.!?;:"


@dataclass
class ReadabilityIssue:
    cue_id: int
    message: str


def chinese_character_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff]", text))


def _break_position(text: str, target: int) -> int:
    if len(text) <= target:
        return len(text)
    lower = max(1, target - 5)
    upper = min(len(text) - 1, target + 5)
    candidates = [
        index + 1
        for index in range(lower, upper)
        if text[index] in PUNCTUATION or text[index].isspace()
    ]
    if candidates:
        return min(candidates, key=lambda index: abs(index - target))
    return target


def wrap_chinese(text: str, *, width: int = 20, max_lines: int = 2) -> str:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if "\n" in text:
        parts = [part.strip() for part in text.splitlines() if part.strip()]
        text = "".join(parts)
    if len(text) <= width:
        return text
    balanced_width = max(width, ceil(len(text) / max_lines))
    lines: list[str] = []
    remaining = text
    while remaining and len(lines) < max_lines - 1:
        position = _break_position(remaining, balanced_width)
        line = remaining[:position].strip()
        remaining = remaining[position:].strip()
        if remaining and remaining[0] in PUNCTUATION and line:
            line += remaining[0]
            remaining = remaining[1:].lstrip()
        lines.append(line)
    if remaining:
        lines.append(remaining)
    return "\n".join(lines)


def readability_pass(
    cues: list[SubtitleCue],
    *,
    width: int = 20,
    max_lines: int = 2,
) -> tuple[list[SubtitleCue], list[ReadabilityIssue]]:
    output: list[SubtitleCue] = []
    issues: list[ReadabilityIssue] = []
    for cue in cues:
        wrapped = wrap_chinese(cue.text, width=width, max_lines=max_lines)
        duration_s = max(0.001, (cue.end_ms - cue.start_ms) / 1000)
        count = chinese_character_count(wrapped)
        if count / duration_s > 10:
            issues.append(ReadabilityIssue(cue.id, "More than 10 Chinese characters per second."))
        if len(wrapped.splitlines()) > max_lines or any(
            len(line) > width * 1.5 for line in wrapped.splitlines()
        ):
            issues.append(
                ReadabilityIssue(cue.id, "Subtitle still exceeds the preferred line length.")
            )
        if duration_s < 0.7:
            issues.append(ReadabilityIssue(cue.id, "Very short subtitle flash."))
        output.append(cue.model_copy(update={"text": wrapped}))
    return output, issues
