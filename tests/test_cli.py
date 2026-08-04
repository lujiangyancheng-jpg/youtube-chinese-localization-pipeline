from __future__ import annotations

import pytest

from youtube_localizer.cli import _configured, normalize_argv
from youtube_localizer.config import AppConfig
from youtube_localizer.errors import InputValidationError
from youtube_localizer.pipeline import process_pipeline


def test_implicit_process_command() -> None:
    assert normalize_argv(["input.mp4"]) == ["process", "input.mp4"]
    assert normalize_argv(["doctor"]) == ["doctor"]
    assert normalize_argv(["--batch", "inputs.txt"]) == ["batch", "inputs.txt"]


def test_cli_configuration_supports_offline_local_transcription() -> None:
    config = _configured(
        None,
        translation_provider="offline",
        translation_direction="zh-to-en",
    )

    assert config.translation.provider == "offline"
    assert config.translation.direction == "zh-to-en"
    assert "prefer_youtube_chinese" not in config.download.model_dump()


def test_cli_configuration_supports_local_ai_without_api_key() -> None:
    config = _configured(None, translation_provider="ollama")

    assert config.translation.provider == "ollama"
    assert config.translation.ollama_endpoint == "http://localhost:11434"


def test_unknown_force_step_is_rejected_before_input_processing() -> None:
    with pytest.raises(InputValidationError, match="transalte"):
        process_pipeline("missing.mp4", AppConfig(), force_steps={"transalte"})
