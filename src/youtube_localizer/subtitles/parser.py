from __future__ import annotations

import re
from pathlib import Path

from ..errors import SubtitleError
from ..models import SubtitleCue
from ..utils.files import atomic_write_text
from ..utils.text import ms_to_srt, timestamp_to_ms

TIME_LINE_RE = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)
ASS_DIALOGUE_RE = re.compile(r"^Dialogue:\s*(?P<fields>.*)$", re.IGNORECASE)


def parse_srt_text(content: str) -> list[SubtitleCue]:
    normalized = content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if not lines:
            continue
        time_index = next((i for i, line in enumerate(lines) if TIME_LINE_RE.search(line)), None)
        if time_index is None:
            continue
        match = TIME_LINE_RE.search(lines[time_index])
        assert match
        text = "\n".join(lines[time_index + 1 :]).strip()
        if not text:
            continue
        try:
            cue = SubtitleCue(
                id=len(cues) + 1,
                start_ms=timestamp_to_ms(match.group("start")),
                end_ms=timestamp_to_ms(match.group("end")),
                text=text,
            )
            cue.validate_timing()
        except ValueError as exc:
            raise SubtitleError(str(exc)) from exc
        cues.append(cue)
    if not cues:
        raise SubtitleError("No valid subtitle cues were found.")
    return cues


def parse_vtt_text(content: str) -> list[SubtitleCue]:
    normalized = content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"^\s*WEBVTT[^\n]*\n", "", normalized, count=1, flags=re.IGNORECASE)
    normalized = re.sub(
        r"(?ms)^(?:NOTE|STYLE|REGION)(?:[^\n]*\n)(?:.*?)(?=\n\s*\n|\Z)", "", normalized
    )
    lines = normalized.splitlines()
    timings = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := TIME_LINE_RE.search(line)) is not None
    ]
    cues: list[SubtitleCue] = []
    for position, (time_index, match) in enumerate(timings):
        next_time_index = timings[position + 1][0] if position + 1 < len(timings) else len(lines)
        payload = lines[time_index + 1 : next_time_index]
        # A standard WebVTT cue identifier can sit between a blank line and the next timing
        # line. Exclude it from the preceding cue while retaining YouTube's leading blank
        # placeholder before actual rolling-caption text.
        blank_positions = [index for index, line in enumerate(payload) if not line.strip()]
        if blank_positions:
            last_blank = blank_positions[-1]
            has_text_before = any(line.strip() for line in payload[:last_blank])
            has_text_after = any(line.strip() for line in payload[last_blank + 1 :])
            if has_text_before and has_text_after:
                payload = payload[:last_blank]
        text = "\n".join(line.rstrip() for line in payload if line.strip()).strip()
        if not text:
            continue
        cue = SubtitleCue(
            id=len(cues) + 1,
            start_ms=timestamp_to_ms(match.group("start")),
            end_ms=timestamp_to_ms(match.group("end")),
            text=text,
        )
        try:
            cue.validate_timing()
        except ValueError as exc:
            raise SubtitleError(str(exc)) from exc
        cues.append(cue)
    if not cues:
        raise SubtitleError("No valid WebVTT cues were found.")
    return cues


def parse_ass_text(content: str) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    for line in content.replace("\ufeff", "").splitlines():
        match = ASS_DIALOGUE_RE.match(line)
        if not match:
            continue
        fields = match.group("fields").split(",", 9)
        if len(fields) < 10:
            continue
        start, end, text = fields[1], fields[2], fields[9]
        text = re.sub(r"\{[^}]*}", "", text).replace(r"\N", "\n").replace(r"\n", "\n").strip()
        if not text:
            continue
        try:
            cue = SubtitleCue(
                id=len(cues) + 1,
                start_ms=timestamp_to_ms(
                    start.replace(".", ",") + ("0" if len(start.rsplit(".", 1)[-1]) == 2 else "")
                ),
                end_ms=timestamp_to_ms(
                    end.replace(".", ",") + ("0" if len(end.rsplit(".", 1)[-1]) == 2 else "")
                ),
                text=text,
            )
            cue.validate_timing()
        except ValueError as exc:
            raise SubtitleError(f"Invalid ASS dialogue timing: {line}") from exc
        cues.append(cue)
    if not cues:
        raise SubtitleError("No valid ASS dialogue cues were found.")
    return cues


def parse_subtitle(path: Path) -> list[SubtitleCue]:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise SubtitleError(f"Cannot read subtitle file {path}: {exc}") from exc
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt_text(content)
    if suffix == ".vtt":
        return parse_vtt_text(content)
    if suffix in {".ass", ".ssa"}:
        return parse_ass_text(content)
    raise SubtitleError(f"Unsupported subtitle format: {suffix}")


def serialize_srt(cues: list[SubtitleCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        cue.validate_timing()
        blocks.append(
            f"{index}\n{ms_to_srt(cue.start_ms)} --> {ms_to_srt(cue.end_ms)}\n{cue.text.strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def write_srt(path: Path, cues: list[SubtitleCue]) -> None:
    if not cues:
        raise SubtitleError("Refusing to write an empty subtitle file.")
    atomic_write_text(path, serialize_srt(cues))
