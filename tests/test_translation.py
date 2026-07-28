from __future__ import annotations

import json

import pytest

from youtube_localizer.errors import TranslationImportError
from youtube_localizer.models import SubtitleCue
from youtube_localizer.translation.manual import (
    parse_imported_translations,
    serialize_translation_batch,
)


@pytest.fixture
def cues() -> list[SubtitleCue]:
    return [
        SubtitleCue(id=1, start_ms=1000, end_ms=2000, text="Hello"),
        SubtitleCue(id=2, start_ms=2100, end_ms=3000, text="Open https://example.com"),
    ]


def test_translation_batch_serialization(cues: list[SubtitleCue]) -> None:
    records = [json.loads(line) for line in serialize_translation_batch(cues).splitlines()]
    assert records[0] == {
        "id": 1,
        "start": "00:00:01,000",
        "end": "00:00:02,000",
        "en": "Hello",
        "zh": "",
    }


def test_translation_import_validates_ids_and_timestamps(cues: list[SubtitleCue]) -> None:
    content = "\n".join(
        [
            '{"id":1,"start":"00:00:01,000","end":"00:00:02,000","en":"Hello","zh":"你好"}',
            '{"id":2,"start":"00:00:02,100","end":"00:00:03,000","en":"Open https://example.com","zh":"打开 https://example.com"}',
        ]
    )
    result = parse_imported_translations(content, cues)
    assert result[1].text == "你好"
    assert result[2].start_ms == cues[1].start_ms


def test_translation_import_rejects_changed_timestamp(cues: list[SubtitleCue]) -> None:
    content = '{"id":1,"start":"00:00:01,100","end":"00:00:02,000","en":"Hello","zh":"你好"}'
    with pytest.raises(TranslationImportError, match="timestamps changed"):
        parse_imported_translations(content, cues)


def test_translation_import_rejects_empty_translation(cues: list[SubtitleCue]) -> None:
    content = '{"id":1,"start":"00:00:01,000","end":"00:00:02,000","en":"Hello","zh":""}'
    with pytest.raises(TranslationImportError, match="empty"):
        parse_imported_translations(content, cues)


def test_translation_import_rejects_changed_url(cues: list[SubtitleCue]) -> None:
    content = (
        '{"id":2,"start":"00:00:02,100","end":"00:00:03,000",'
        '"en":"Open https://example.com","zh":"打开 https://example.cn"}'
    )
    with pytest.raises(TranslationImportError, match="URL"):
        parse_imported_translations(content, cues)
