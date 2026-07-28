from __future__ import annotations

import html
import re

from ..models import SubtitleCue

TAG_RE = re.compile(r"</?(?:c(?:\.[^ >]+)?|v|lang|ruby|rt|b|i|u|font)(?:\s+[^>]*)?>", re.IGNORECASE)
POSITION_RE = re.compile(r"\{\\[^}]+\}")
SPACE_RE = re.compile(r"[ \t\u00a0]+")
WORD_RE = re.compile(r"\S+")
SOUND_RE = re.compile(r"^\s*[\[(].+[\])]\s*$")


def clean_caption_text(text: str, *, preserve_sound_descriptions: bool = True) -> str:
    text = html.unescape(text)
    text = TAG_RE.sub("", text)
    text = POSITION_RE.sub("", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("♪", " ").replace("♫", " ")
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = " ".join(line for line in lines if line)
    text = SPACE_RE.sub(" ", text).strip()
    if not preserve_sound_descriptions and SOUND_RE.match(text):
        return ""
    return text


def _word_overlap(left: str, right: str) -> int:
    left_words = WORD_RE.findall(left)
    right_words = WORD_RE.findall(right)
    maximum = min(len(left_words), len(right_words))
    for size in range(maximum, 0, -1):
        if [word.casefold() for word in left_words[-size:]] == [
            word.casefold() for word in right_words[:size]
        ]:
            return size
    return 0


def remove_rolling_overlap(previous: str, current: str) -> str:
    if previous.casefold() == current.casefold():
        return ""
    if current.casefold().startswith(previous.casefold() + " "):
        return current[len(previous) :].strip()
    overlap = _word_overlap(previous, current)
    if overlap >= 2:
        words = WORD_RE.findall(current)
        return " ".join(words[overlap:]).strip()
    return current


def normalize_cues(
    cues: list[SubtitleCue],
    *,
    preserve_sound_descriptions: bool = True,
) -> list[SubtitleCue]:
    normalized: list[SubtitleCue] = []
    previous_full_text = ""
    for cue in cues:
        start_ms = max(0, cue.start_ms)
        end_ms = max(0, cue.end_ms)
        if start_ms >= end_ms:
            continue
        full_text = clean_caption_text(
            cue.text, preserve_sound_descriptions=preserve_sound_descriptions
        )
        if not full_text:
            continue
        text = (
            remove_rolling_overlap(previous_full_text, full_text)
            if previous_full_text
            else full_text
        )
        previous_full_text = full_text
        if not text:
            continue
        if normalized and normalized[-1].text.casefold() == text.casefold():
            normalized[-1].end_ms = max(normalized[-1].end_ms, end_ms)
            continue
        normalized.append(
            SubtitleCue(
                id=len(normalized) + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                confidence=cue.confidence,
            )
        )
    return normalized


def validate_cues(cues: list[SubtitleCue]) -> list[str]:
    errors: list[str] = []
    for index, cue in enumerate(cues, start=1):
        if cue.id != index:
            errors.append(f"Cue position {index} has non-sequential ID {cue.id}.")
        if cue.start_ms < 0:
            errors.append(f"Cue {cue.id} has a negative start time.")
        if cue.start_ms >= cue.end_ms:
            errors.append(f"Cue {cue.id} does not end after it starts.")
        if not cue.text.strip():
            errors.append(f"Cue {cue.id} is empty.")
        if index > 1:
            previous = cues[index - 2]
            if previous.text.strip() == cue.text.strip():
                errors.append(f"Cues {previous.id} and {cue.id} are exact adjacent duplicates.")
    return errors
