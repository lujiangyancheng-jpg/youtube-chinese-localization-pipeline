from __future__ import annotations

import json
import zipfile

import pytest

from youtube_localizer.errors import LocalizerError
from youtube_localizer.translation.offline import (
    install_offline_model_archive,
    select_offline_translation_device,
    validate_offline_model,
)


def _write_fake_model_archive(path, *, source_code="en", target_code="zh") -> None:
    root = f"translate-{source_code}_{target_code}-test"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{root}/metadata.json",
            json.dumps(
                {
                    "package_version": "test",
                    "from_code": source_code,
                    "to_code": target_code,
                }
            ),
        )
        archive.writestr(f"{root}/sentencepiece.model", b"fake-tokenizer")
        archive.writestr(f"{root}/model/config.json", "{}")
        archive.writestr(f"{root}/model/model.bin", b"fake-model")


def test_automatic_offline_translation_prefers_reliable_cpu() -> None:
    assert select_offline_translation_device("auto") == "cpu"
    assert select_offline_translation_device("cpu") == "cpu"
    assert select_offline_translation_device("cuda") == "cuda"


def test_install_offline_model_archive_validates_and_installs_atomically(tmp_path) -> None:
    archive = tmp_path / "model.argosmodel"
    destination = tmp_path / "installed-model"
    _write_fake_model_archive(archive)

    installed = install_offline_model_archive(archive, destination)

    assert installed == destination
    assert validate_offline_model(destination)["package_version"] == "test"
    assert not list(tmp_path.glob(".installed-model.install-*"))


def test_install_offline_model_archive_rejects_path_traversal(tmp_path) -> None:
    archive = tmp_path / "unsafe.argosmodel"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside.txt", "unsafe")

    with pytest.raises(LocalizerError, match="unsafe path"):
        install_offline_model_archive(archive, tmp_path / "model")
    assert not (tmp_path.parent / "outside.txt").exists()


def test_install_offline_model_archive_supports_chinese_to_english(tmp_path) -> None:
    archive = tmp_path / "zh-en.argosmodel"
    destination = tmp_path / "translate-zh_en"
    _write_fake_model_archive(archive, source_code="zh", target_code="en")

    installed = install_offline_model_archive(
        archive,
        destination,
        source_code="zh",
        target_code="en",
    )

    metadata = validate_offline_model(
        installed,
        source_code="zh",
        target_code="en",
    )
    assert metadata is not None
    assert metadata["from_code"] == "zh"
    assert metadata["to_code"] == "en"
