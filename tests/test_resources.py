from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from youtube_localizer.resources import (
    bundled_fonts_directory,
    find_bundled_model,
    resolve_whisper_model,
)


def test_bundled_model_resolution_uses_configured_model_root(tmp_path, monkeypatch) -> None:
    model = tmp_path / "faster-whisper-medium"
    model.mkdir()
    monkeypatch.setenv("YOUTUBE_LOCALIZER_MODELS", str(tmp_path))

    assert find_bundled_model("faster-whisper-medium") == model.resolve()
    reference, local_only = resolve_whisper_model("medium")
    assert reference == str(model.resolve())
    assert local_only is True


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
