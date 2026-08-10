from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

from ..models import SubtitleCue


@dataclass(frozen=True)
class SubtitleQualityFinding:
    cue_id: int
    category: str
    message: str


def _visible_text(text: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", text).strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text))


def _cjk_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff]", text))


def audit_subtitles(
    cues: list[SubtitleCue],
    *,
    language: str,
    max_lines: int,
    preferred_line_length: int,
) -> dict[str, object]:
    """Return deterministic, review-oriented subtitle checks for the final target track.

    These are warnings rather than automatic rewrites. A sentence can be intentionally fast,
    so the report helps a person inspect only the risky cues instead of silently altering timing.
    """
    findings: list[SubtitleQualityFinding] = []
    previous_visible = ""
    is_chinese = language.lower().startswith("zh")
    for cue in cues:
        visible = _visible_text(cue.text)
        if not visible:
            continue
        duration_seconds = max(0.001, (cue.end_ms - cue.start_ms) / 1000)
        lines = [line for line in cue.text.splitlines() if line.strip()]
        if duration_seconds < 0.7:
            findings.append(
                SubtitleQualityFinding(cue.id, "flash", "Very short subtitle flash (under 0.7s).")
            )
        if len(lines) > max_lines:
            findings.append(
                SubtitleQualityFinding(
                    cue.id,
                    "line_count",
                    f"Uses {len(lines)} lines; the selected style prefers at most {max_lines}.",
                )
            )
        if any(len(line) > preferred_line_length * 1.5 for line in lines):
            findings.append(
                SubtitleQualityFinding(
                    cue.id,
                    "line_length",
                    "A subtitle line still exceeds the preferred display width.",
                )
            )
        if is_chinese:
            reading_speed = _cjk_count(visible) / duration_seconds
            if reading_speed > 10:
                findings.append(
                    SubtitleQualityFinding(
                        cue.id,
                        "reading_speed",
                        f"Chinese reading speed is {reading_speed:.1f} characters/second (preferred ≤10).",
                    )
                )
        else:
            reading_speed = _word_count(visible) / duration_seconds
            if reading_speed > 4.5:
                findings.append(
                    SubtitleQualityFinding(
                        cue.id,
                        "reading_speed",
                        f"English reading speed is {reading_speed:.1f} words/second (preferred ≤4.5).",
                    )
                )
        normalized = re.sub(r"\s+", " ", visible).casefold()
        if normalized and normalized == previous_visible:
            findings.append(
                SubtitleQualityFinding(
                    cue.id,
                    "duplicate",
                    "Same visible text as the previous subtitle cue.",
                )
            )
        previous_visible = normalized

    category_counts = Counter(finding.category for finding in findings)
    flagged_cue_ids = sorted({finding.cue_id for finding in findings})
    return {
        "target_language": language,
        "total_cues": len(cues),
        "flagged_cue_ids": flagged_cue_ids,
        "flagged_cue_count": len(flagged_cue_ids),
        "finding_count": len(findings),
        "findings_by_category": dict(sorted(category_counts.items())),
        "findings": [asdict(finding) for finding in findings],
    }
