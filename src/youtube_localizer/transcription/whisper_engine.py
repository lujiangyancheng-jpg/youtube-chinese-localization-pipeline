from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from ..config import TranscriptionConfig
from ..errors import LocalizerError
from ..models import SubtitleCue
from ..subtitles.cleanup import CleanupResult, cleanup_english
from ..subtitles.parser import write_srt
from ..utils.files import atomic_write_json

LOGGER = logging.getLogger(__name__)


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except (ImportError, RuntimeError):
        return False


def resolve_device_and_compute(config: TranscriptionConfig) -> tuple[str, str]:
    device = config.device
    if device == "auto":
        device = "cuda" if cuda_available() else "cpu"
    compute = config.compute_type
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def transcribe_audio(
    audio_path: Path,
    output_json: Path,
    output_srt: Path,
    config: TranscriptionConfig,
) -> CleanupResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise LocalizerError(
            "faster-whisper is not installed. Install a supported Python 3.11-3.13 environment "
            'and run: python -m pip install -e ".[transcription]"'
        ) from exc

    device, compute_type = resolve_device_and_compute(config)
    if device == "cpu" and config.model.lower() in {"large", "large-v2", "large-v3"}:
        LOGGER.warning(
            "A large Whisper model was selected on CPU. This may be very slow and require "
            "substantial RAM; medium or small is recommended."
        )
    try:
        model = WhisperModel(config.model, device=device, compute_type=compute_type)
        segments_iterator, info = model.transcribe(
            str(audio_path),
            language="en",
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
            word_timestamps=config.word_timestamps,
        )
        raw_segments: list[dict[str, Any]] = []
        cues: list[SubtitleCue] = []
        for index, segment in enumerate(segments_iterator, start=1):
            text = segment.text.strip()
            if not text:
                continue
            confidence = None
            if segment.avg_logprob is not None:
                confidence = min(1.0, max(0.0, math.exp(float(segment.avg_logprob))))
            words = [
                {
                    "start": word.start,
                    "end": word.end,
                    "word": word.word,
                    "probability": word.probability,
                }
                for word in (segment.words or [])
            ]
            raw_segments.append(
                {
                    "id": index,
                    "start": segment.start,
                    "end": segment.end,
                    "text": text,
                    "avg_logprob": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob,
                    "words": words,
                }
            )
            start_ms = max(0, round(segment.start * 1000))
            end_ms = max(start_ms + 1, round(segment.end * 1000))
            cues.append(
                SubtitleCue(
                    id=len(cues) + 1,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    confidence=confidence,
                )
            )
        if not cues:
            raise LocalizerError(
                "Whisper found no English speech. Check the source audio stream and language."
            )
        raw = {
            "model": config.model,
            "device": device,
            "compute_type": compute_type,
            "language": getattr(info, "language", "en"),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": raw_segments,
        }
        atomic_write_json(output_json, raw)
        cleanup = cleanup_english(cues)
        write_srt(output_srt, cleanup.cues)
        return cleanup
    except LocalizerError:
        raise
    except RuntimeError as exc:
        message = str(exc)
        if "out of memory" in message.lower() or "cuda" in message.lower():
            raise LocalizerError(
                "Whisper ran out of GPU memory or CUDA failed. Retry with transcription.device=cpu, "
                "a smaller model, or a less memory-intensive compute_type."
            ) from exc
        raise LocalizerError(f"Whisper transcription failed: {exc}") from exc
