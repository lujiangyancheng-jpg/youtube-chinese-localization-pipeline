from __future__ import annotations

import pytest

from youtube_localizer.config import load_config
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
    assert config.download.prefer_youtube_chinese is True
    assert config.download.format == "bestvideo+bestaudio/best"
    assert config.download.format_sort == ["res", "fps", "br", "size"]
    assert config.translation.direction == "en-to-zh"
    assert config.translation.offline_zh_en_model_directory.name == "translate-zh_en-1_9"
    assert config.translation.offline_device == "auto"


def test_configuration_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("mystery_setting: true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        load_config(path)
