from __future__ import annotations

import pytest

from youtube_localizer.config import AppConfig
from youtube_localizer.errors import ConfigurationError
from youtube_localizer.profiles import apply_processing_profile


def test_balanced_profile_uses_hardware_encoding_without_changing_workflow() -> None:
    config = AppConfig.model_validate(
        {
            "subtitle_mode": "bilingual_en_zh",
            "translation": {"provider": "offline", "direction": "en-to-zh"},
            "subtitles": {"font": "LXGW WenKai"},
        }
    )

    profiled = apply_processing_profile(config, "balanced")

    assert profiled.transcription.model == "medium"
    assert profiled.transcription.beam_size == 5
    assert profiled.render.codec == "h264_nvenc"
    assert profiled.translation.provider == "offline"
    assert profiled.subtitle_mode == "bilingual_en_zh"
    assert profiled.subtitles.font == "LXGW WenKai"


def test_safe_cpu_profile_caps_workload() -> None:
    profiled = apply_processing_profile(AppConfig(), "safe_cpu")

    assert profiled.transcription.model == "small"
    assert profiled.transcription.device == "cpu"
    assert profiled.transcription.compute_type == "int8"
    assert profiled.transcription.beam_size == 1
    assert profiled.render.codec == "libx264"
    assert profiled.render.preset == "veryfast"


def test_profile_name_is_validated() -> None:
    with pytest.raises(ConfigurationError, match="Unknown processing profile"):
        apply_processing_profile(AppConfig(), "turbo")  # type: ignore[arg-type]
