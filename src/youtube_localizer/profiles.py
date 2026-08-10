from __future__ import annotations

from typing import Literal

from .config import AppConfig
from .errors import ConfigurationError

ProcessingProfile = Literal["auto", "fast", "balanced", "quality", "safe_cpu"]
OutputQuality = Literal["best", "high", "standard"]

PROCESSING_PROFILES: tuple[ProcessingProfile, ...] = (
    "auto",
    "fast",
    "balanced",
    "quality",
    "safe_cpu",
)
OUTPUT_QUALITIES: tuple[OutputQuality, ...] = ("best", "high", "standard")


def apply_processing_profile(config: AppConfig, profile: ProcessingProfile) -> AppConfig:
    """Apply a bounded performance/quality preset without touching user workflow choices.

    Translation provider, language direction, subtitle design, output location, and API settings
    always remain untouched. NVENC is deliberately allowed to fall back to libx264 when the
    installed FFmpeg or GPU cannot use it.
    """
    if profile not in PROCESSING_PROFILES:
        raise ConfigurationError(
            "Unknown processing profile: "
            f"{profile}. Expected one of: {', '.join(PROCESSING_PROFILES)}."
        )

    if profile == "auto":
        # Keep device selection automatic: faster-whisper selects CUDA when the bundled runtime
        # is ready and retries on CPU when it is not. NVENC similarly falls back to libx264.
        # This is the only profile used by the desktop UI, so users do not have to understand
        # encoder/recognition trade-offs before getting a high-quality result.
        transcription = config.transcription.model_copy(
            update={"model": "medium", "device": "auto", "compute_type": "auto", "beam_size": 5}
        )
        render = config.render.model_copy(
            update={"codec": "h264_nvenc", "crf": 17, "preset": "medium"}
        )
    elif profile == "safe_cpu":
        transcription = config.transcription.model_copy(
            update={"model": "small", "device": "cpu", "compute_type": "int8", "beam_size": 1}
        )
        render = config.render.model_copy(
            update={"codec": "libx264", "crf": 22, "preset": "veryfast"}
        )
    elif profile == "fast":
        transcription = config.transcription.model_copy(
            update={"model": "small", "beam_size": 1}
        )
        render = config.render.model_copy(
            update={"codec": "h264_nvenc", "crf": 23, "preset": "medium"}
        )
    elif profile == "quality":
        transcription = config.transcription.model_copy(
            update={"model": "medium", "beam_size": 8, "vad_filter": True, "word_timestamps": True}
        )
        render = config.render.model_copy(
            update={"codec": "h264_nvenc", "crf": 17, "preset": "medium"}
        )
    else:  # balanced
        transcription = config.transcription.model_copy(
            update={"model": "medium", "beam_size": 5}
        )
        render = config.render.model_copy(
            update={"codec": "h264_nvenc", "crf": 19, "preset": "medium"}
        )

    return config.model_copy(update={"transcription": transcription, "render": render})


def apply_output_quality(config: AppConfig, quality: OutputQuality) -> AppConfig:
    """Set the final encode quality without changing source download or acceleration behavior."""
    if quality not in OUTPUT_QUALITIES:
        raise ConfigurationError(
            "Unknown output quality: "
            f"{quality}. Expected one of: {', '.join(OUTPUT_QUALITIES)}."
        )

    crf_by_quality = {"best": 17, "high": 19, "standard": 23}
    render = config.render.model_copy(update={"crf": crf_by_quality[quality]})
    return config.model_copy(update={"render": render})
