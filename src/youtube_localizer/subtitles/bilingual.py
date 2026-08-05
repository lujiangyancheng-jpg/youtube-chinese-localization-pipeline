from __future__ import annotations

from ..errors import SubtitleError
from ..models import SubtitleCue


def _overlap_ms(left: SubtitleCue, right: SubtitleCue) -> int:
    return max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))


def align_cues_to_reference(
    reference: list[SubtitleCue],
    candidates: list[SubtitleCue],
) -> list[SubtitleCue]:
    """Project candidate text onto a reference timeline using temporal overlap.

    Independently authored YouTube language tracks rarely share cue boundaries.  The target
    language remains the timing authority while overlapping source-language text is combined
    onto each target cue.  A nearest cue is used only when the tracks contain a small gap.
    """
    if not reference or not candidates:
        raise SubtitleError("Both subtitle tracks are required for bilingual alignment.")

    aligned: list[SubtitleCue] = []
    for cue in reference:
        overlaps = [candidate for candidate in candidates if _overlap_ms(cue, candidate) > 0]
        if not overlaps:
            midpoint = (cue.start_ms + cue.end_ms) / 2
            overlaps = [
                min(
                    candidates,
                    key=lambda candidate: abs(
                        ((candidate.start_ms + candidate.end_ms) / 2) - midpoint
                    ),
                )
            ]

        texts: list[str] = []
        for candidate in overlaps:
            text = " ".join(candidate.text.split())
            if text and (not texts or texts[-1].casefold() != text.casefold()):
                texts.append(text)
        if not texts:
            raise SubtitleError(f"Could not align bilingual cue {cue.id}.")
        aligned.append(cue.model_copy(update={"text": " ".join(texts)}))
    return aligned


def align_bilingual_tracks(
    english: list[SubtitleCue],
    chinese: list[SubtitleCue],
    *,
    reference_language: str,
) -> tuple[list[SubtitleCue], list[SubtitleCue]]:
    """Return tracks with identical IDs/timestamps, preserving the target timeline."""
    already_aligned = len(english) == len(chinese) and all(
        en.id == zh.id and en.start_ms == zh.start_ms and en.end_ms == zh.end_ms
        for en, zh in zip(english, chinese, strict=True)
    )
    if already_aligned:
        return english, chinese
    if reference_language == "zh":
        return align_cues_to_reference(chinese, english), chinese
    if reference_language == "en":
        return english, align_cues_to_reference(english, chinese)
    raise SubtitleError(f"Unsupported bilingual reference language: {reference_language}")


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
