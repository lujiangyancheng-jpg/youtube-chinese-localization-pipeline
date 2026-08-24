from __future__ import annotations

import json

from youtube_localizer.desktop_settings import (
    DesktopSettings,
    desktop_settings_path,
    load_desktop_settings,
    save_desktop_settings,
)


def test_settings_round_trip_without_secrets(tmp_path) -> None:
    path = tmp_path / "desktop-settings.json"
    settings = DesktopSettings(
        direction="zh-to-en",
        subtitle_mode="bilingual_en_zh",
        translation_provider="ollama",
        font_size=56,
        subtitle_x_percent=45,
        subtitle_y_percent=84,
        output_quality="high",
        output_fps=60,
        output_height=2160,
        output_directory="D:/Localized",
        update_channel="stable",
        resume=False,
    )

    assert save_desktop_settings(settings, settings_path=path) == path
    assert load_desktop_settings(settings_path=path) == settings
    assert "api_key" not in json.loads(path.read_text(encoding="utf-8"))


def test_invalid_settings_are_safely_normalized(tmp_path) -> None:
    path = tmp_path / "desktop-settings.json"
    path.write_text(
        json.dumps(
            {
                "direction": "unsupported",
                "font_size": 500,
                "subtitle_x_percent": -12,
                "subtitle_y_percent": "bottom",
                "output_fps": 144,
                "output_height": 900,
                "resume": "yes",
            }
        ),
        encoding="utf-8",
    )

    settings = load_desktop_settings(settings_path=path)

    assert settings.direction == "en-to-zh"
    assert settings.font_size == 96
    assert settings.subtitle_x_percent == 2
    assert settings.subtitle_y_percent == 96
    assert settings.output_fps is None
    assert settings.output_height is None
    assert settings.resume is True


def test_corrupt_settings_fall_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "desktop-settings.json"
    path.write_text("{not-json", encoding="utf-8")

    settings = load_desktop_settings(settings_path=path)

    assert settings.output_quality == "best"
    assert settings.output_directory
    assert settings.update_channel == "stable"


def test_settings_path_uses_local_app_data() -> None:
    path = desktop_settings_path({"LOCALAPPDATA": "C:/AppData/Local"})

    assert path.as_posix().endswith("YouTube Chinese Localizer/desktop-settings.json")
