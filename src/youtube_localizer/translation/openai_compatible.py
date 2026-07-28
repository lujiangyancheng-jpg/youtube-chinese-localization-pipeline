from __future__ import annotations

import json
import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..errors import LocalizerError, TranslationImportError
from ..models import SubtitleCue
from ..utils.text import ms_to_srt
from .base import TranslationContext, TranslationProvider
from .cache import TranslationCache
from .manual import parse_imported_translations
from .prompts import TRANSLATION_RULES, context_prompt


class RetryableAPIError(LocalizerError):
    pass


class OpenAICompatibleProvider(TranslationProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        cache: TranslationCache,
        api_key: str | None = None,
        timeout: float = 120,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.cache = cache
        self.api_key = api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
        self.timeout = timeout
        if not self.endpoint or not self.model or not self.api_key:
            raise LocalizerError(
                "OpenAI-compatible translation requires endpoint, model, and "
                "OPENAI_COMPATIBLE_API_KEY. ChatGPT Plus does not include API credits; "
                "use the manual provider to avoid separate API billing."
            )

    def _url(self) -> str:
        return (
            self.endpoint
            if self.endpoint.endswith("/chat/completions")
            else f"{self.endpoint}/chat/completions"
        )

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RetryableAPIError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            self._url(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableAPIError(
                f"Translation API temporarily failed with HTTP {response.status_code}."
            )
        if response.is_error:
            raise LocalizerError(
                f"Translation API failed with HTTP {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def translate_batch(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
    ) -> list[SubtitleCue]:
        records = [
            {
                "id": cue.id,
                "start": ms_to_srt(cue.start_ms),
                "end": ms_to_srt(cue.end_ms),
                "en": cue.text,
                "zh": "",
            }
            for cue in cues
        ]
        cache_payload = {
            "provider": "openai-compatible",
            "endpoint": self.endpoint,
            "model": self.model,
            "context": context_prompt(context),
            "records": records,
        }
        key = self.cache.key(cache_payload)
        cached = self.cache.get(key)
        if cached:
            content = str(cached["content"])
        else:
            payload = {
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": TRANSLATION_RULES},
                    {
                        "role": "user",
                        "content": context_prompt(context)
                        + "\n\nJSONL:\n"
                        + "\n".join(json.dumps(item, ensure_ascii=False) for item in records),
                    },
                ],
            }
            data = self._request(payload)
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise TranslationImportError(
                    "Translation API returned no message content."
                ) from exc
            self.cache.put(
                key,
                {
                    "content": content,
                    "usage": data.get("usage", {}),
                },
            )
        parsed = parse_imported_translations(content, cues)
        if set(parsed) != {cue.id for cue in cues}:
            missing = sorted({cue.id for cue in cues} - set(parsed))
            raise TranslationImportError(f"Translation response omitted cue IDs: {missing}")
        return [parsed[cue.id] for cue in cues]
