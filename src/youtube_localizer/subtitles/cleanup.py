from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import SubtitleCue


@dataclass
class CleanupResult:
    cues: list[SubtitleCue]
    warnings: list[str]
    flagged_cue_ids: list[int]


def cleanup_english(cues: list[SubtitleCue]) -> CleanupResult:
    cleaned: list[SubtitleCue] = []
    warnings: list[str] = []
    flagged: list[int] = []
    for cue in cues:
        text = re.sub(r"\s+([,.;:!?])", r"\1", cue.text)
        text = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        duration_s = (cue.end_ms - cue.start_ms) / 1000
        words = len(text.split())
        if len(text) > 120 or (duration_s > 0 and words / duration_s > 4.5):
            warnings.append(f"Cue {cue.id} may be too long for its display duration.")
            flagged.append(cue.id)
        if cue.confidence is not None and cue.confidence < 0.55:
            warnings.append(f"Cue {cue.id} has low ASR confidence ({cue.confidence:.2f}).")
            flagged.append(cue.id)
        cleaned.append(cue.model_copy(update={"text": text}))
    return CleanupResult(cleaned, warnings, sorted(set(flagged)))
