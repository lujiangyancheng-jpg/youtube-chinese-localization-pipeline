from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from youtube_localizer.resources import (
    application_icon_path,
    bundled_fonts_directory,
    cuda_runtime_directories,
    find_bundled_model,
    installed_whisper_models,
    nvenc_compatibility_ffmpeg,
    package_tier,
    resolve_whisper_model,
    super_resolution_runtime,
)


def test_application_icon_uses_installed_bundle(tmp_path, monkeypatch) -> None:
    icon = tmp_path / "assets" / "app-icon.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"png")
    monkeypatch.setenv("YOUTUBE_LOCALIZER_HOME", str(tmp_path))

    assert application_icon_path() == icon.resolve()


def test_bundled_model_resolution_uses_configured_model_root(tmp_path, monkeypatch) -> None:
    model = tmp_path / "faster-whisper-medium"
    model.mkdir()
    monkeypatch.setenv("YOUTUBE_LOCALIZER_MODELS", str(tmp_path))

    assert find_bundled_model("faster-whisper-medium") == model.resolve()
    reference, local_only = resolve_whisper_model("medium")
    assert reference == str(model.resolve())
    assert local_only is True


def test_installed_whisper_models_lists_available_model_packs(tmp_path, monkeypatch) -> None:
    (tmp_path / "faster-whisper-small").mkdir()
    (tmp_path / "faster-whisper-medium").mkdir()
    monkeypatch.setenv("YOUTUBE_LOCALIZER_MODELS", str(tmp_path))

    assert installed_whisper_models() == ("small", "medium")


def test_package_tier_uses_the_installer_marker(tmp_path, monkeypatch) -> None:
    (tmp_path / "package-tier.txt").write_text("standard\n", encoding="utf-8")
    monkeypatch.delenv("YOUTUBE_LOCALIZER_PACKAGE_TIER", raising=False)
    monkeypatch.setenv("YOUTUBE_LOCALIZER_HOME", str(tmp_path))

    assert package_tier() == "standard"


def test_whisper_size_remains_downloadable_without_a_bundle() -> None:
    with patch("youtube_localizer.resources.model_roots", return_value=[]):
        reference, local_only = resolve_whisper_model("small")

    assert reference == "small"
    assert local_only is False


def test_explicit_whisper_directory_is_always_local(tmp_path) -> None:
    model = Path(tmp_path) / "custom-whisper"
    model.mkdir()

    reference, local_only = resolve_whisper_model(str(model))

    assert reference == str(model.resolve())
    assert local_only is True


def test_bundled_font_resolution_uses_configured_font_root(tmp_path, monkeypatch) -> None:
    font = tmp_path / "NotoSansCJKsc-Regular.otf"
    font.write_bytes(b"font")
    monkeypatch.setenv("YOUTUBE_LOCALIZER_FONTS", str(tmp_path))

    assert bundled_fonts_directory() == tmp_path.resolve()


def test_cuda_runtime_directories_finds_ollama_cuda_12_runtime(tmp_path, monkeypatch) -> None:
    ollama = tmp_path / "runtime" / "ollama" / "ollama.exe"
    cuda = ollama.parent / "lib" / "ollama" / "cuda_v12"
    cuda.mkdir(parents=True)
    ollama.parent.mkdir(parents=True, exist_ok=True)
    ollama.write_bytes(b"")
    (cuda / "cublas64_12.dll").write_bytes(b"")
    monkeypatch.setenv("OLLAMA_PATH", str(ollama))

    assert cuda_runtime_directories() == [cuda.resolve()]


def test_nvenc_compatibility_ffmpeg_uses_the_installed_bundle(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "runtime" / "ffmpeg-nvenc-compat" / "bin" / "ffmpeg.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setenv("YOUTUBE_LOCALIZER_HOME", str(tmp_path))

    assert nvenc_compatibility_ffmpeg() == executable.resolve()


def test_super_resolution_runtime_uses_the_installed_optional_pack(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "runtime" / "super-resolution"
    (runtime / "models-upconv_7_photo").mkdir(parents=True)
    (runtime / "models-cunet").mkdir()
    (runtime / "models-upconv_7_photo" / "noise1_scale2.0x_model.param").write_text("")
    (runtime / "models-cunet" / "noise1_scale2.0x_model.param").write_text("")
    executable = runtime / "waifu2x-ncnn-vulkan.exe"
    executable.write_bytes(b"exe")
    monkeypatch.setenv("YOUTUBE_LOCALIZER_HOME", str(tmp_path))
    monkeypatch.delenv("VIDEO_LOCALIZER_UPSCALER_PATH", raising=False)

    assert super_resolution_runtime() == (executable.resolve(), runtime.resolve())
