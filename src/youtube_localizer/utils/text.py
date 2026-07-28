from __future__ import annotations

import re

TIMESTAMP_RE = re.compile(r"^\s*(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{2})[,.](?P<ms>\d{3})\s*$")


def timestamp_to_ms(value: str) -> int:
    match = TIMESTAMP_RE.match(value)
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value!r}")
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis = int(match.group("ms"))
    if minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid subtitle timestamp: {value!r}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def ms_to_srt(value: int) -> str:
    value = max(0, int(value))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def ms_to_ass(value: int) -> str:
    value = max(0, int(value))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    centiseconds = millis // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
