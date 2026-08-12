from __future__ import annotations

import json
import zipfile

import pytest

from youtube_localizer.errors import LocalizerError
from youtube_localizer.models import SubtitleCue
from youtube_localizer.translation.offline import (
    enforce_glossary,
    group_paragraph_cues,
    group_sentence_cues,
    install_offline_model_archive,
    paragraph_translation_to_cues,
    select_offline_translation_device,
    split_group_translation,
    validate_offline_model,
)


def test_local_ai_grouping_uses_larger_complete_paragraphs_to_reduce_model_requests() -> None:
    from youtube_localizer.pipeline import _group_local_ai_paragraphs

    cues = [
        SubtitleCue(
            id=index,
            start_ms=(index - 1) * 800,
            end_ms=index * 800,
            text=f"fragment {index}",
        )
        for index in range(1, 37)
    ]

    groups = _group_local_ai_paragraphs(cues, source_code="en")

    assert len(groups) == 1
    assert len(groups[0]) == 36


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


def test_sentence_fragments_are_grouped_and_split_back_to_original_cues() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="The first big"),
        SubtitleCue(id=2, start_ms=1000, end_ms=2000, text="name arrives today."),
    ]

    groups = group_sentence_cues(cues, source_code="en")
    parts = split_group_translation(
        "第一位大人物今天到达。",
        groups[0],
        source_code="en",
        target_code="zh",
    )

    assert groups == [cues]
    assert parts is not None
    assert len(parts) == 2
    assert "".join(parts) == "第一位大人物今天到达。"


def test_rolling_captions_are_grouped_as_complete_paragraphs() -> None:
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=4000, text="Welcome back."),
        SubtitleCue(id=2, start_ms=4010, end_ms=8000, text="The transfer market is"),
        SubtitleCue(id=3, start_ms=8010, end_ms=12_000, text="very busy today."),
        SubtitleCue(id=4, start_ms=12_010, end_ms=16_000, text="Here is the first story."),
        SubtitleCue(id=5, start_ms=16_010, end_ms=20_000, text="Stay tuned."),
        SubtitleCue(id=6, start_ms=20_010, end_ms=24_000, text="Next paragraph starts."),
    ]

    groups = group_paragraph_cues(cues, source_code="en", target_sentences=4)

    assert [[cue.id for cue in group] for group in groups] == [[1, 2, 3, 4, 5], [6]]


def test_complete_paragraph_translation_is_resegmented_at_target_punctuation() -> None:
    source = [
        SubtitleCue(id=1, start_ms=1000, end_ms=4000, text="Welcome back."),
        SubtitleCue(id=2, start_ms=4010, end_ms=9000, text="Transfer news follows."),
    ]

    translated = paragraph_translation_to_cues(
        "欢迎回来。接下来是今天的转会市场新闻。",
        source,
        target_code="zh",
        max_characters=20,
    )

    assert [cue.text for cue in translated] == ["欢迎回来。", "接下来是今天的转会市场新闻。"]
    assert translated[0].start_ms == 1000
    assert translated[-1].end_ms == 9000
    assert translated[0].end_ms == translated[1].start_ms


def test_paragraph_resegmentation_never_orphans_final_punctuation() -> None:
    source = [SubtitleCue(id=1, start_ms=0, end_ms=5000, text="Long source sentence.")]

    translated = paragraph_translation_to_cues(
        "这是一段长度刚好会在限制附近结束的中文翻译内容，必须把最后的句号留在前一句。",
        source,
        target_code="zh",
        max_characters=20,
    )

    assert translated[-1].text != "。"
    assert translated[-1].text.endswith("。")


def test_offline_glossary_replaces_the_models_default_term() -> None:
    glossary = {"Xabi Alonso": "哈维·阿隆索"}
    source = "Xabi Alonso is in the dugout."

    assert (
        enforce_glossary(
            source,
            "萨比·阿隆索在教练席。",
            glossary,
            target_code="zh",
            default_translations={"Xabi Alonso": "萨比·阿隆索"},
        )
        == "哈维·阿隆索在教练席。"
    )
