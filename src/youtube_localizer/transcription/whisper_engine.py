from __future__ import annotations

import ctypes
import logging
import math
import os
from pathlib import Path
from typing import Any

from ..config import TranscriptionConfig
from ..errors import LocalizerError
from ..models import SubtitleCue
from ..resource_gate import heavy_workload_slot
from ..resources import cuda_runtime_directories, resolve_whisper_model
from ..subtitles.cleanup import CleanupResult, cleanup_english
from ..subtitles.parser import write_srt
from ..utils.files import atomic_write_json

LOGGER = logging.getLogger(__name__)
CUDA_12_LIBRARIES = ("cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll")
_CUDA_DLL_DIRECTORY_HANDLES: list[Any] = []
_CUDA_DLL_DIRECTORIES: set[str] = set()


def _configure_windows_cuda_runtime() -> list[Path]:
    """Make the bundled CUDA 12 runtime visible before CTranslate2 starts."""
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return []

    configured: list[Path] = []
    for directory in cuda_runtime_directories():
        key = str(directory).casefold()
        if key not in _CUDA_DLL_DIRECTORIES:
            try:
                # Keep the handle alive for the full process lifetime.  Otherwise
                # Windows may remove the directory before lazy CUDA loading starts.
                _CUDA_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
                _CUDA_DLL_DIRECTORIES.add(key)
            except OSError as exc:
                LOGGER.debug("Could not register CUDA runtime directory %s: %s", directory, exc)
                continue
        configured.append(directory)
    return configured


def cuda_runtime_status() -> tuple[bool, str]:
    """Return whether faster-whisper can safely use the detected NVIDIA GPU."""
    runtime_directories = _configure_windows_cuda_runtime()
    try:
        import ctranslate2
    except ImportError:
        return False, "CTranslate2 is not installed"

    try:
        device_count = ctranslate2.get_cuda_device_count()
    except RuntimeError as exc:
        return False, f"CUDA device probe failed: {exc}"
    if device_count < 1:
        return False, "no NVIDIA CUDA device was detected"

    if os.name == "nt":
        missing: list[str] = []
        for library in CUDA_12_LIBRARIES:
            try:
                ctypes.WinDLL(library)
            except OSError:
                missing.append(library)
        if missing:
            location = (
                f" (checked bundled runtime: {', '.join(str(path) for path in runtime_directories)})"
                if runtime_directories
                else ""
            )
            return False, f"missing CUDA 12 runtime library: {', '.join(missing)}{location}"

    return True, f"{device_count} CUDA device(s) ready"


def cuda_available() -> bool:
    return cuda_runtime_status()[0]


def resolve_device_and_compute(config: TranscriptionConfig) -> tuple[str, str]:
    device = config.device
    if device == "auto":
        cuda_ready, cuda_reason = cuda_runtime_status()
        device = "cuda" if cuda_ready else "cpu"
        if not cuda_ready:
            LOGGER.info(
                "Whisper GPU acceleration is unavailable (%s); starting directly on CPU (int8).",
                cuda_reason,
            )
    elif device == "cuda":
        cuda_ready, cuda_reason = cuda_runtime_status()
        if not cuda_ready:
            raise LocalizerError(
                "CUDA transcription was explicitly selected, but its runtime is not ready: "
                f"{cuda_reason}. Select CPU or reinstall the offline package."
            )
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
        cpu_threads=config.cpu_threads if device == "cpu" else 0,
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
    with heavy_workload_slot("Whisper transcription"):
        return _transcribe_audio(audio_path, output_json, output_srt, config, language=language)


def _transcribe_audio(
    audio_path: Path,
    output_json: Path,
    output_srt: Path,
    config: TranscriptionConfig,
    *,
    language: str = "en",
) -> CleanupResult:
    device, compute_type = resolve_device_and_compute(config)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise LocalizerError(
            "faster-whisper is not installed. Install a supported Python 3.11-3.13 environment "
            'and run: python -m pip install -e ".[transcription]"'
        ) from exc

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
