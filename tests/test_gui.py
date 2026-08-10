from __future__ import annotations

import os
from pathlib import Path

import pytest

from youtube_localizer.gui import (
    SUBTITLE_FONTS,
    api_configuration,
    build_process_command,
    gui_process_creationflags,
    local_ai_available,
    mode_description,
    progress_update_from_output,
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


def test_build_process_command_passes_selected_processing_profile() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        processing_profile="quality",
    )

    assert command[command.index("--processing-profile") + 1] == "quality"


def test_build_process_command_passes_smart_output_controls() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        processing_profile="auto",
        output_quality="best",
        output_fps=60,
        output_height=2160,
    )

    assert command[command.index("--processing-profile") + 1] == "auto"
    assert command[command.index("--output-quality") + 1] == "best"
    assert command[command.index("--output-fps") + 1] == "60"
    assert command[command.index("--output-height") + 1] == "2160"


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


def test_mode_description_explains_download_only_and_local_ai() -> None:
    assert "不生成字幕" in mode_description("download_only", "ollama")
    assert "完整段落" in mode_description("chinese", "ollama")
    assert "API Key" in mode_description("chinese", "openai-compatible")


def test_progress_updates_show_real_download_translation_and_rendering_progress() -> None:
    value, message = progress_update_from_output(
        "[download] 50.0% of 20MiB", provider="ollama"
    ) or (None, "")
    assert value == 11.0
    assert message == "正在下载原视频：50.0%"

    value, message = progress_update_from_output(
        "INFO Local AI translating paragraph 12/24…", provider="ollama"
    ) or (None, "")
    assert value == 47.0 + 28.0 * 11 / 24
    assert message == "本地 AI 翻译：12/24 段"

    value, message = progress_update_from_output(
        "INFO Rendering subtitles: 75.0%", provider="ollama"
    ) or (None, "")
    assert value == 93.5
    assert message == "正在压制字幕：75.0%"


def test_windows_gui_process_hides_its_console() -> None:
    if os.name == "nt":
        import subprocess

        flags = gui_process_creationflags()
        assert flags & subprocess.CREATE_NEW_PROCESS_GROUP
        assert flags & subprocess.CREATE_NO_WINDOW
    else:
        assert gui_process_creationflags() == 0
