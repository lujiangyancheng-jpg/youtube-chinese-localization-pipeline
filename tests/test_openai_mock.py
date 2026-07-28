from __future__ import annotations

from unittest.mock import patch

from youtube_localizer.models import SubtitleCue
from youtube_localizer.translation.base import TranslationContext
from youtube_localizer.translation.cache import TranslationCache
from youtube_localizer.translation.openai_compatible import OpenAICompatibleProvider


def test_openai_compatible_provider_parses_and_caches(tmp_path) -> None:
    cue = SubtitleCue(id=1, start_ms=0, end_ms=1000, text="Hello")
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"id":1,"start":"00:00:00,000","end":"00:00:01,000",'
                        '"en":"Hello","zh":"你好"}'
                    )
                }
            }
        ],
        "usage": {"total_tokens": 12},
    }
    provider = OpenAICompatibleProvider(
        endpoint="https://api.example.test/v1",
        model="test-model",
        api_key="test-secret",
        cache=TranslationCache(tmp_path / "cache"),
    )
    with patch.object(provider, "_request", return_value=response) as request:
        first = provider.translate_batch([cue], TranslationContext(title="Demo"))
        second = provider.translate_batch([cue], TranslationContext(title="Demo"))
    assert first[0].text == "你好"
    assert second[0].text == "你好"
    request.assert_called_once()
