from __future__ import annotations

from pathlib import Path

import pytest

from youtube_localizer.gui import api_configuration, build_process_command


def test_build_process_command_uses_argument_array_and_resume() -> None:
    command = build_process_command(
        " https://www.youtube.com/watch?v=abc123 ",
        subtitle_mode="chinese",
        translation_provider="manual",
        python_executable="python.exe",
        main_script=Path("main.py"),
    )

    assert command == [
        "python.exe",
        "main.py",
        "process",
        "https://www.youtube.com/watch?v=abc123",
        "--subtitle-mode",
        "chinese",
        "--translation-provider",
        "manual",
        "--translation-direction",
        "en-to-zh",
        "--prefer-youtube-chinese",
        "--resume",
    ]


def test_build_process_command_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="请粘贴"):
        build_process_command(
            " ",
            subtitle_mode="chinese",
            translation_provider="manual",
        )
    with pytest.raises(ValueError, match="字幕模式"):
        build_process_command(
            "video.mp4",
            subtitle_mode="unknown",
            translation_provider="manual",
        )


def test_api_configuration_does_not_require_or_mutate_environment() -> None:
    environment = {
        "OPENAI_COMPATIBLE_ENDPOINT": "https://example.test/v1",
        "OPENAI_COMPATIBLE_MODEL": "example-model",
        "OPENAI_COMPATIBLE_API_KEY": "secret",
    }

    assert api_configuration(environment) == (
        "https://example.test/v1",
        "example-model",
        "secret",
    )
    assert environment["OPENAI_COMPATIBLE_API_KEY"] == "secret"


def test_build_process_command_supports_offline_without_youtube_chinese() -> None:
    command = build_process_command(
        "https://youtu.be/abc123def45",
        subtitle_mode="bilingual_en_zh",
        translation_provider="offline",
        translation_direction="zh-to-en",
        prefer_youtube_chinese=False,
        resume=False,
        python_executable="python.exe",
        main_script=Path("main.py"),
    )

    assert "offline" in command
    assert command[command.index("--translation-direction") + 1] == "zh-to-en"
    assert "--no-prefer-youtube-chinese" in command
    assert "--resume" not in command
