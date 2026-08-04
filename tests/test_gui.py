from __future__ import annotations

from pathlib import Path

import pytest

from youtube_localizer.gui import (
    SUBTITLE_FONTS,
    api_configuration,
    build_process_command,
    local_ai_available,
)


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
        "--subtitle-font",
        "Noto Sans CJK SC",
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


def test_build_process_command_supports_offline_local_transcription() -> None:
    command = build_process_command(
        "https://youtu.be/abc123def45",
        subtitle_mode="bilingual_en_zh",
        translation_provider="offline",
        translation_direction="zh-to-en",
        resume=False,
        python_executable="python.exe",
        main_script=Path("main.py"),
    )

    assert "offline" in command
    assert command[command.index("--translation-direction") + 1] == "zh-to-en"
    assert not any("youtube-chinese" in argument for argument in command)
    assert "--resume" not in command


def test_build_process_command_supports_local_ai_without_api_key() -> None:
    command = build_process_command(
        "https://youtu.be/abc123def45",
        subtitle_mode="chinese",
        translation_provider="ollama",
        python_executable="python.exe",
        main_script=Path("main.py"),
    )

    assert command[command.index("--translation-provider") + 1] == "ollama"
    assert isinstance(local_ai_available(), bool)


def test_build_process_command_passes_selected_bundled_font() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        subtitle_font="LXGW WenKai",
    )

    assert command[command.index("--subtitle-font") + 1] == "LXGW WenKai"
    assert {"Noto Sans CJK SC", "Noto Serif CJK SC", "LXGW WenKai"}.issubset(
        SUBTITLE_FONTS.values()
    )


def test_build_process_command_supports_direct_download_without_subtitles() -> None:
    command = build_process_command(
        "https://youtu.be/abc123def45",
        subtitle_mode="download_only",
        translation_provider="offline",
    )

    assert command[command.index("--subtitle-mode") + 1] == "download_only"
