from __future__ import annotations

import os
from pathlib import Path

import pytest

from youtube_localizer.gui import (
    DEFAULT_SUBTITLE_FONT,
    SUBTITLE_FONT_SIZES,
    SUBTITLE_FONTS,
    api_configuration,
    build_process_command,
    clamp_subtitle_preview_values,
    gui_process_creationflags,
    local_ai_available,
    mode_description,
    packaged_app_needs_onboarding,
    progress_update_from_output,
    queue_input_values,
    whisper_model_installation_message,
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


def test_queue_input_values_keeps_local_paths_and_deduplicates_lines() -> None:
    assert queue_input_values("  https://youtu.be/one  \nC:/Videos/My clip.mp4\nhttps://youtu.be/one\n") == [
        "https://youtu.be/one",
        "C:/Videos/My clip.mp4",
    ]


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


def test_build_process_command_passes_preview_position_and_manual_size() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        subtitle_font_size=59,
        subtitle_position_x=37,
        subtitle_position_y=81,
    )

    assert command[command.index("--subtitle-font-size") + 1] == "59"
    assert command[command.index("--subtitle-position-x") + 1] == "37"
    assert command[command.index("--subtitle-position-y") + 1] == "81"


def test_subtitle_preview_values_are_clamped_to_renderer_safe_ranges() -> None:
    assert clamp_subtitle_preview_values(-1, 101, 121) == (2, 98, 120)


def test_build_process_command_passes_the_selected_output_directory() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        output_directory=Path("D:/Localized videos"),
    )

    assert command[command.index("--output-dir") + 1] == str(Path("D:/Localized videos"))


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


def test_build_process_command_uses_the_single_bundled_font_and_selected_size() -> None:
    command = build_process_command(
        "video.mp4",
        subtitle_mode="chinese",
        translation_provider="offline",
        subtitle_font=DEFAULT_SUBTITLE_FONT,
        subtitle_font_size=SUBTITLE_FONT_SIZES["大号（56）"],
    )

    assert command[command.index("--subtitle-font") + 1] == DEFAULT_SUBTITLE_FONT
    assert command[command.index("--subtitle-font-size") + 1] == "56"
    assert tuple(SUBTITLE_FONTS.values()) == (DEFAULT_SUBTITLE_FONT,)


def test_build_process_command_rejects_an_unsafe_subtitle_font_size() -> None:
    with pytest.raises(ValueError, match="12"):
        build_process_command(
            "video.mp4",
            subtitle_mode="chinese",
            translation_provider="offline",
            subtitle_font_size=121,
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
        "INFO Preflight ready: package=standard", provider="offline"
    ) or (None, "")
    assert value == 2.0
    assert "检查硬件" in message

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


def test_gui_explains_when_a_packaged_install_has_no_whisper_model(monkeypatch) -> None:
    monkeypatch.setattr("youtube_localizer.gui.package_tier", lambda: "standard")
    monkeypatch.setattr("youtube_localizer.gui.installed_whisper_models", lambda: ())

    message = whisper_model_installation_message()

    assert message is not None
    assert "Whisper Small" in message
    assert "首次设置" in message


def test_packaged_app_only_shows_first_run_guide_once(monkeypatch) -> None:
    monkeypatch.setattr("youtube_localizer.gui.package_tier", lambda: "standard")
    monkeypatch.setattr("youtube_localizer.gui.onboarding_completed", lambda: False)
    assert packaged_app_needs_onboarding()

    monkeypatch.setattr("youtube_localizer.gui.onboarding_completed", lambda: True)
    assert not packaged_app_needs_onboarding()
