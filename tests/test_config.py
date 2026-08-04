from __future__ import annotations

import pytest

from youtube_localizer.config import load_config, validate_config_data
from youtube_localizer.errors import ConfigurationError


def test_load_configuration_overrides_defaults(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "output_directory: localized\ntranscription:\n  model: small\n  device: cpu\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert str(config.output_directory) == "localized"
    assert config.transcription.model == "small"
    assert config.render.codec == "libx264"
    assert config.download.format == "bestvideo+bestaudio/best"
    assert config.download.format_sort == ["res", "fps", "br", "size"]
    assert config.translation.direction == "en-to-zh"
    assert config.translation.offline_zh_en_model_directory.name == "translate-zh_en-1_9"
    assert config.translation.offline_device == "auto"
    assert config.translation.ollama_model == "qwen3:4b"
    assert config.translation.ollama_endpoint == "http://localhost:11434"


def test_retired_youtube_subtitle_setting_is_ignored_for_saved_projects() -> None:
    config = validate_config_data({"download": {"prefer_youtube_chinese": True}})

    assert "prefer_youtube_chinese" not in config.download.model_dump()


def test_configuration_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("mystery_setting: true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        load_config(path)
