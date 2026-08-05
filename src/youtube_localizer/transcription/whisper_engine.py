from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from ..config import TranscriptionConfig
from ..errors import LocalizerError
from ..models import SubtitleCue
from ..resources import resolve_whisper_model
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


def _is_cuda_runtime_failure(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    indicators = (
        "cuda",
        "cublas",
        "cudnn",
        "nvrtc",
        "nvidia",
        "out of memory",
    )
    return any(indicator in message for indicator in indicators)


def _run_whisper_attempt(
    model_class: Any,
    model_reference: str | Path,
    audio_path: Path,
    config: TranscriptionConfig,
    *,
    language: str,
    device: str,
    compute_type: str,
    local_only: bool,
) -> tuple[list[dict[str, Any]], list[SubtitleCue], Any]:
    model = model_class(
        model_reference,
        device=device,
        compute_type=compute_type,
        local_files_only=local_only,
    )
    segments_iterator, info = model.transcribe(
        str(audio_path),
        language=language,
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
            f"Whisper found no {language} speech. Check the source audio stream and language."
        )
    return raw_segments, cues, info


def transcribe_audio(
    audio_path: Path,
    output_json: Path,
    output_srt: Path,
    config: TranscriptionConfig,
    *,
    language: str = "en",
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
        model_reference, local_only = resolve_whisper_model(config.model)
        if local_only:
            LOGGER.info("Using bundled Whisper model at %s.", model_reference)
        attempts = [(device, compute_type)]
        if device == "cuda":
            attempts.append(("cpu", "int8"))
        used_fallback = False
        for attempt_device, attempt_compute_type in attempts:
            try:
                raw_segments, cues, info = _run_whisper_attempt(
                    WhisperModel,
                    model_reference,
                    audio_path,
                    config,
                    language=language,
                    device=attempt_device,
                    compute_type=attempt_compute_type,
                    local_only=local_only,
                )
                device = attempt_device
                compute_type = attempt_compute_type
                break
            except RuntimeError as exc:
                if attempt_device != "cuda" or not _is_cuda_runtime_failure(exc):
                    raise
                used_fallback = True
                LOGGER.warning(
                    "Whisper CUDA execution failed; automatically retrying on CPU (int8). "
                    "No CUDA installation is required. Details: %s",
                    exc,
                )
        else:  # pragma: no cover - every attempt either returns or raises
            raise LocalizerError("Whisper did not complete a transcription attempt.")
        raw = {
            "model": config.model,
            "device": device,
            "compute_type": compute_type,
            "cuda_fallback": used_fallback,
            "language": getattr(info, "language", language),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": raw_segments,
        }
        atomic_write_json(output_json, raw)
        if language == "en":
            cleanup = cleanup_english(cues)
        else:
            warnings: list[str] = []
            flagged: list[int] = []
            for cue in cues:
                if cue.confidence is not None and cue.confidence < 0.55:
                    warnings.append(f"Cue {cue.id} has low ASR confidence ({cue.confidence:.2f}).")
                    flagged.append(cue.id)
            cleanup = CleanupResult(cues, warnings, flagged)
        write_srt(output_srt, cleanup.cues)
        return cleanup
    except LocalizerError:
        raise
    except RuntimeError as exc:
        if _is_cuda_runtime_failure(exc):
            raise LocalizerError(
                "Whisper could not complete after automatic CUDA/CPU device handling. "
                f"Try a smaller model. Details: {exc}"
            ) from exc
        raise LocalizerError(f"Whisper transcription failed: {exc}") from exc
