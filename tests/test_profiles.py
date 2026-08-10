from __future__ import annotations

import pytest

from youtube_localizer.config import AppConfig
from youtube_localizer.errors import ConfigurationError
from youtube_localizer.profiles import apply_output_quality, apply_processing_profile


def test_auto_profile_keeps_device_detection_and_auto_selects_hardware_encoding() -> None:
    profiled = apply_processing_profile(AppConfig(), "auto")

    assert profiled.transcription.model == "medium"
    assert profiled.transcription.device == "auto"
    assert profiled.transcription.compute_type == "auto"
    assert profiled.render.codec == "auto"
    assert profiled.render.crf == 17


def test_output_quality_changes_only_final_encode_quality() -> None:
    config = AppConfig.model_validate({"render": {"output_fps": 60, "output_height": 2160}})

    profiled = apply_output_quality(config, "high")

    assert profiled.render.crf == 19
    assert profiled.render.output_fps == 60
    assert profiled.render.output_height == 2160


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
    assert profiled.render.codec == "auto"
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
