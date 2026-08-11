from __future__ import annotations

import pytest

from youtube_localizer.cli import _configured, _run_batch_item, normalize_argv
from youtube_localizer.config import AppConfig
from youtube_localizer.errors import InputValidationError, LocalizerError
from youtube_localizer.models import ProjectPaths, SourceMetadata, SubtitleCue
from youtube_localizer.pipeline import process_pipeline, save_project_config
from youtube_localizer.reporting import build_report, write_report
from youtube_localizer.state import PipelineState
from youtube_localizer.subtitles.parser import write_srt
from youtube_localizer.utils.files import atomic_write_json, load_json


def test_implicit_process_command() -> None:
    assert normalize_argv(["input.mp4"]) == ["process", "input.mp4"]
    assert normalize_argv(["doctor"]) == ["doctor"]
    assert normalize_argv(["preflight", "input.mp4"]) == ["preflight", "input.mp4"]
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


def test_cli_configuration_overrides_subtitle_font() -> None:
    config = _configured(None, subtitle_font=" LXGW WenKai ")

    assert config.subtitles.font == "LXGW WenKai"


def test_cli_configuration_overrides_subtitle_font_size() -> None:
    config = _configured(None, subtitle_font_size=56)

    assert config.subtitles.font_size == 56
    assert config.subtitles.english_font_size == 40


def test_cli_configuration_rejects_unsafe_subtitle_font_size() -> None:
    with pytest.raises(LocalizerError, match="12"):
        _configured(None, subtitle_font_size=121)


def test_cli_configuration_overrides_subtitle_preview_position() -> None:
    config = _configured(None, subtitle_position_x=33, subtitle_position_y=76)

    assert config.subtitles.position_x_percent == 33
    assert config.subtitles.position_y_percent == 76


def test_cli_configuration_rejects_an_unsafe_subtitle_preview_position() -> None:
    with pytest.raises(LocalizerError, match="position-x"):
        _configured(None, subtitle_position_x=99)


def test_cli_configuration_supports_download_only_mode() -> None:
    config = _configured(None, subtitle_mode="download_only")

    assert config.subtitle_mode == "download_only"


def test_cli_configuration_applies_processing_profile() -> None:
    config = _configured(None, processing_profile="fast")

    assert config.transcription.model == "small"
    assert config.render.codec == "auto"


def test_cli_configuration_supports_smart_high_quality_output_controls() -> None:
    config = _configured(
        None,
        processing_profile="auto",
        output_quality="best",
        output_fps=60,
        output_height=2160,
    )

    assert config.transcription.device == "auto"
    assert config.render.codec == "auto"
    assert config.render.crf == 17
    assert config.render.output_fps == 60
    assert config.render.output_height == 2160


def test_batch_worker_returns_a_failure_without_stopping_other_queued_projects(monkeypatch) -> None:
    monkeypatch.setattr(
        "youtube_localizer.cli.process_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(LocalizerError("expected failure")),
    )

    outcome = _run_batch_item("https://youtu.be/batch-test", AppConfig(), resume=True)

    assert outcome.status == "failed"
    assert outcome.error == "expected failure"


def test_unknown_force_step_is_rejected_before_input_processing() -> None:
    with pytest.raises(InputValidationError, match="transalte"):
        process_pipeline("missing.mp4", AppConfig(), force_steps={"transalte"})


def test_render_command_keeps_earlier_warnings_and_softsub_failure(tmp_path, monkeypatch) -> None:
    from youtube_localizer import cli

    project = ProjectPaths(tmp_path / "project")
    project.create()
    source = project.source / "source_video.mp4"
    source.write_bytes(b"source")
    metadata = SourceMetadata(
        source_type="local",
        source_input=str(source),
        video_id="render-context",
        title="Render context",
        duration=1.0,
        subtitle_kind="faster-whisper (local English transcription)",
    )
    atomic_write_json(project.metadata, metadata.model_dump(mode="json"))
    config = AppConfig.model_validate({"publishing": {"generate_metadata": False}})
    save_project_config(project, config)
    write_srt(project.chinese_srt, [SubtitleCue(id=1, start_ms=0, end_ms=1000, text="测试")])
    old_output = project.source / "metadata.raw.json"
    old_output.write_text("{}", encoding="utf-8")
    state = PipelineState(project.state_file)
    previous = build_report(
        metadata,
        state.data,
        warnings=["Earlier transcription warning."],
        output_paths=[old_output],
    )
    write_report(project.logs, previous)

    def fake_hardsub(active_project, _config):
        active_project.chinese_hardsub.write_bytes(b"hard subtitles")
        return active_project.chinese_hardsub

    monkeypatch.setattr(cli, "render_project", fake_hardsub)
    monkeypatch.setattr(
        cli,
        "render_softsub_project",
        lambda *_args: (_ for _ in ()).throw(LocalizerError("container is incompatible")),
    )

    cli.render_command(project.root)

    report = load_json(project.logs / "report.json")
    assert "Earlier transcription warning." in report["warnings"]
    assert any("Selectable subtitle MP4 was not created" in item for item in report["warnings"])
    assert str(old_output.resolve()) in report["output_paths"]
    assert str(project.chinese_hardsub.resolve()) in report["output_paths"]
