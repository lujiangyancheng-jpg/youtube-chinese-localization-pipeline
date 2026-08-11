from __future__ import annotations

from youtube_localizer.config import AppConfig
from youtube_localizer.hardware import NvidiaGPU, SystemResources
from youtube_localizer.models import SourceMetadata
from youtube_localizer.preflight import build_job_preflight


def _metadata(tmp_path) -> SourceMetadata:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    return SourceMetadata(
        source_type="local",
        source_input=str(source),
        video_id="preflight",
        title="Preflight",
        duration=60,
        height=1080,
    )


def test_standard_bundle_uses_bundled_small_and_fast_translation(tmp_path, monkeypatch) -> None:
    from youtube_localizer import preflight

    small = tmp_path / "models" / "faster-whisper-small"
    small.mkdir(parents=True)
    en_zh = tmp_path / "models" / "translate-en_zh-1_9"
    en_zh.mkdir()
    monkeypatch.setenv("YOUTUBE_LOCALIZER_PACKAGE_TIER", "standard")
    monkeypatch.setattr(
        preflight,
        "find_bundled_model",
        lambda name: {"faster-whisper-small": small, "translate-en_zh-1_9": en_zh}.get(name),
    )
    monkeypatch.setattr(preflight, "detect_system_resources", lambda: SystemResources(8, 16 * 1024))
    monkeypatch.setattr(preflight, "query_nvidia_gpus", lambda: [])

    plan = build_job_preflight(
        _metadata(tmp_path),
        AppConfig.model_validate({"translation": {"provider": "ollama"}}),
    )

    assert plan.ready
    assert plan.package == "standard"
    assert plan.config.transcription.model == "small"
    assert plan.config.translation.provider == "offline"
    assert any("fully offline" in warning for warning in plan.warnings)


def test_low_available_vram_switches_auto_medium_to_small(tmp_path, monkeypatch) -> None:
    from youtube_localizer import preflight

    small = tmp_path / "models" / "faster-whisper-small"
    small.mkdir(parents=True)
    medium = tmp_path / "models" / "faster-whisper-medium"
    medium.mkdir()
    monkeypatch.setattr(
        preflight,
        "find_bundled_model",
        lambda name: {
            "faster-whisper-small": small,
            "faster-whisper-medium": medium,
        }.get(name),
    )
    monkeypatch.setattr(preflight, "detect_system_resources", lambda: SystemResources(16, 32 * 1024))
    monkeypatch.setattr(
        preflight,
        "query_nvidia_gpus",
        lambda: [NvidiaGPU("RTX", "1", 8 * 1024, 3 * 1024)],
    )

    plan = build_job_preflight(_metadata(tmp_path), AppConfig())

    assert plan.config.transcription.model == "small"
    assert any("VRAM" in warning for warning in plan.warnings)


def test_source_checkout_keeps_a_user_selected_local_ai_provider(tmp_path, monkeypatch) -> None:
    from youtube_localizer import preflight

    small = tmp_path / "models" / "faster-whisper-small"
    small.mkdir(parents=True)
    monkeypatch.delenv("YOUTUBE_LOCALIZER_PACKAGE_TIER", raising=False)
    monkeypatch.setattr(preflight, "find_bundled_model", lambda name: {"faster-whisper-small": small}.get(name))
    monkeypatch.setattr(preflight, "detect_system_resources", lambda: SystemResources(16, 32 * 1024))
    monkeypatch.setattr(preflight, "query_nvidia_gpus", lambda: [])

    plan = build_job_preflight(
        _metadata(tmp_path),
        AppConfig.model_validate({"translation": {"provider": "ollama"}}),
    )

    assert plan.package == "source checkout"
    assert plan.config.transcription.model == "medium"
    assert plan.config.translation.provider == "ollama"


def test_preflight_blocks_a_job_that_cannot_fit_on_the_output_disk(tmp_path, monkeypatch) -> None:
    from youtube_localizer import preflight

    monkeypatch.setattr(preflight, "detect_system_resources", lambda: SystemResources(8, 16 * 1024))
    monkeypatch.setattr(preflight, "query_nvidia_gpus", lambda: [])
    monkeypatch.setattr(preflight, "_output_free_bytes", lambda _directory: 1024)

    plan = build_job_preflight(_metadata(tmp_path), AppConfig())

    assert not plan.ready
    assert plan.blockers
