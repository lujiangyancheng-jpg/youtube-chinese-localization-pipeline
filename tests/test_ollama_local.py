from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from youtube_localizer.errors import LocalizerError
from youtube_localizer.models import SubtitleCue
from youtube_localizer.translation.base import TranslationContext
from youtube_localizer.translation.cache import TranslationCache
from youtube_localizer.translation.ollama_local import (
    LocalOllamaProvider,
    validate_local_ollama_endpoint,
)


def _response(payload: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_local_ai_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(LocalizerError, match="only accepts.*this computer"):
        validate_local_ollama_endpoint("https://example.com")


def test_local_ai_translates_a_complete_paragraph_and_caches_it(tmp_path) -> None:
    tags = _response({"models": [{"name": "qwen3:4b"}]})
    translation = _response(
        {
            "message": {
                "content": json.dumps(
                    {"translation": "欢迎回来。今天聊聊转会市场。"},
                    ensure_ascii=False,
                )
            }
        }
    )
    cues = [
        SubtitleCue(id=1, start_ms=0, end_ms=1000, text="Welcome back."),
        SubtitleCue(id=2, start_ms=1000, end_ms=2500, text="Today: the transfer market."),
    ]
    with (
        patch("youtube_localizer.translation.ollama_local.httpx.get", return_value=tags),
        patch(
            "youtube_localizer.translation.ollama_local.httpx.post",
            return_value=translation,
        ) as post,
    ):
        provider = LocalOllamaProvider(
            endpoint="http://localhost:11434",
            model="qwen3:4b",
            auto_pull=True,
            cache=TranslationCache(tmp_path / "cache"),
            source_code="en",
            target_code="zh",
        )
        first = provider.translate_paragraph(cues, TranslationContext(title="Football news"))
        second = provider.translate_paragraph(cues, TranslationContext(title="Football news"))

    assert first == "欢迎回来。今天聊聊转会市场。"
    assert second == first
    assert post.call_count == 1
    request_payload = post.call_args.kwargs["json"]
    assert request_payload["think"] is False
    assert "continuous spoken paragraph" in request_payload["messages"][0]["content"]
    assert request_payload["format"]["required"] == ["translation"]


def test_local_ai_retries_runaway_translation_output(tmp_path) -> None:
    tags = _response({"models": [{"name": "qwen3:4b"}]})
    runaway = _response(
        {"message": {"content": json.dumps({"translation": "1. " * 1000})}}
    )
    recovered = _response(
        {"message": {"content": json.dumps({"translation": "自然的完整段落。"})}}
    )
    cues = [SubtitleCue(id=1, start_ms=0, end_ms=3000, text="A complete paragraph.")]
    with (
        patch("youtube_localizer.translation.ollama_local.httpx.get", return_value=tags),
        patch(
            "youtube_localizer.translation.ollama_local.httpx.post",
            side_effect=[runaway, recovered],
        ) as post,
    ):
        provider = LocalOllamaProvider(
            endpoint="http://localhost:11434",
            model="qwen3:4b",
            auto_pull=False,
            cache=TranslationCache(tmp_path / "cache"),
            source_code="en",
            target_code="zh",
        )
        translated = provider.translate_paragraph(cues, TranslationContext())

    assert translated == "自然的完整段落。"
    assert post.call_count == 2
