from __future__ import annotations

from typing import Literal

from .config import AppConfig
from .errors import ConfigurationError

ProcessingProfile = Literal["fast", "balanced", "quality", "safe_cpu"]

PROCESSING_PROFILES: tuple[ProcessingProfile, ...] = (
    "fast",
    "balanced",
    "quality",
    "safe_cpu",
)


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

    if profile == "safe_cpu":
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
