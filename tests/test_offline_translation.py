from __future__ import annotations

import json
import zipfile

import pytest

from youtube_localizer.errors import LocalizerError
from youtube_localizer.translation.offline import (
    install_offline_model_archive,
    validate_offline_model,
)


def _write_fake_model_archive(path) -> None:
    root = "translate-en_zh-test"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{root}/metadata.json",
            json.dumps(
                {
                    "package_version": "test",
                    "from_code": "en",
                    "to_code": "zh",
                }
            ),
        )
        archive.writestr(f"{root}/sentencepiece.model", b"fake-tokenizer")
        archive.writestr(f"{root}/model/config.json", "{}")
        archive.writestr(f"{root}/model/model.bin", b"fake-model")


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
