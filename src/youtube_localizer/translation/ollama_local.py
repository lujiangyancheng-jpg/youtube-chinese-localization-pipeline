from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from ..errors import LocalizerError
from ..models import SubtitleCue
from .base import TranslationContext, TranslationProvider
from .cache import TranslationCache

LOGGER = logging.getLogger(__name__)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_local_ollama_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise LocalizerError(
            "Local AI translation only accepts an Ollama endpoint on this computer "
            "(for example http://localhost:11434)."
        )
    return normalized


def _translation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translation": {"type": "string", "minLength": 1},
        },
        "required": ["translation"],
        "additionalProperties": False,
    }


class LocalOllamaProvider(TranslationProvider):
    """Translate complete subtitle paragraphs with a local Ollama model."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        auto_pull: bool,
        cache: TranslationCache,
        source_code: str,
        target_code: str,
        timeout: float = 600,
    ) -> None:
        self.endpoint = validate_local_ollama_endpoint(endpoint)
        self.model = model.strip()
        if not self.model:
            raise LocalizerError("A local Ollama model name is required.")
        self.auto_pull = auto_pull
        self.cache = cache
        self.source_code = source_code
        self.target_code = target_code
        self.timeout = timeout
        self._ensure_model()
        LOGGER.info("Local AI paragraph translation ready with Ollama model %s.", self.model)

    def _get_models(self) -> set[str]:
        try:
            response = httpx.get(f"{self.endpoint}/api/tags", timeout=10)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalizerError(
                "Local AI translation could not reach Ollama. Install and start Ollama, then "
                "retry. Windows install: winget install Ollama.Ollama"
            ) from exc
        models = payload.get("models", []) if isinstance(payload, dict) else []
        return {
            str(item.get("name") or item.get("model"))
            for item in models
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        }

    def _ensure_model(self) -> None:
        installed = self._get_models()
        if self.model in installed or (
            ":" not in self.model and f"{self.model}:latest" in installed
        ):
            return
        if not self.auto_pull:
            raise LocalizerError(
                f"Local Ollama model {self.model!r} is not installed. Run: "
                f"ollama pull {self.model}"
            )
        LOGGER.info(
            "Downloading local AI model %s for first use; this may take several minutes…",
            self.model,
        )
        try:
            response = httpx.post(
                f"{self.endpoint}/api/pull",
                json={"model": self.model, "stream": False},
                timeout=max(3600, self.timeout),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LocalizerError(
                f"Could not download local Ollama model {self.model!r}: {exc}"
            ) from exc
        LOGGER.info("Local AI model %s downloaded.", self.model)

    def _messages(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
        *,
        correction: str = "",
    ) -> list[dict[str, str]]:
        source_name = "Simplified Chinese" if self.source_code == "zh" else "English"
        target_name = "natural English" if self.target_code == "en" else "natural Simplified Chinese"
        glossary = (
            "\nRequired terminology (use these target forms exactly):\n"
            + json.dumps(context.glossary, ensure_ascii=False)
            if context.glossary
            else ""
        )
        system = (
            f"You are a professional audiovisual translator from {source_name} to "
            f"{target_name}. Read every cue as one continuous spoken paragraph before "
            "translating. Produce one complete, fluent paragraph. Translate meaning and tone "
            "naturally instead of word by word. "
            "Preserve every fact, name, number, and relationship; do not summarize, omit, "
            "explain ambiguities, add translator notes, or add information. Correct obvious "
            "speech-recognition phrasing only when the surrounding context makes it clear. "
            "If a cue contains an obvious near-homophone or misspelling of the listed channel "
            "or speaker name, use the correct context name. "
            "The video title and channel are context only: never translate, repeat, or prepend "
            "them. Translate only the text between the subtitle paragraph markers. Return only "
            "the complete paragraph translation in the supplied JSON field."
            + glossary
        )
        separator = "" if self.source_code == "zh" else " "
        paragraph = separator.join(cue.text.strip() for cue in cues)
        user = (
            "Context only (do not output):\n"
            f"Video title: {context.title}\n"
            f"Channel/speaker: {context.channel}\n"
            f"Source language: {self.source_code}; target language: {self.target_code}\n"
            "<subtitle_paragraph>\n"
            f"{paragraph}\n"
            "</subtitle_paragraph>"
        )
        if correction:
            user += f"\nPrevious response was invalid: {correction}. Return only the translation."
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _request(self, cues: list[SubtitleCue], context: TranslationContext) -> str:
        correction = ""
        for attempt in range(2):
            try:
                response = httpx.post(
                    f"{self.endpoint}/api/chat",
                    json={
                        "model": self.model,
                        "messages": self._messages(cues, context, correction=correction),
                        "stream": False,
                        "think": False,
                        "format": _translation_schema(),
                        "options": {
                            "temperature": 0.1,
                            "num_ctx": 8192,
                            "num_predict": 1024,
                            "repeat_penalty": 1.1,
                        },
                        "keep_alive": "10m",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
                parsed = json.loads(content)
                translation = str(parsed["translation"]).strip()
                self._validate_translation(translation, cues)
                return translation
            except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                correction = str(exc)
                if attempt == 1:
                    raise LocalizerError(
                        f"Local AI paragraph translation failed after validation retry: {exc}"
                    ) from exc
        raise AssertionError("unreachable")

    def _validate_translation(self, translation: str, cues: list[SubtitleCue]) -> None:
        if not translation:
            raise ValueError("blank paragraph translation")
        source_length = sum(len(cue.text) for cue in cues)
        expansion_limit = 8 if self.target_code == "en" else 3
        maximum_length = max(240, source_length * expansion_limit)
        if len(translation) > maximum_length:
            raise ValueError(
                f"paragraph translation is implausibly long ({len(translation)} characters)"
            )
        if len(re.findall(r"(?:^|\s)\d+[.)]", translation)) > 12:
            raise ValueError("paragraph translation contains a runaway numbered sequence")

    def translate_paragraph(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
    ) -> str:
        payload = {
            "provider": "ollama-paragraph-v1",
            "model": self.model,
            "source_code": self.source_code,
            "target_code": self.target_code,
            "title": context.title,
            "texts": [{"id": cue.id, "text": cue.text} for cue in cues],
            "glossary": context.glossary,
        }
        key = self.cache.key(payload)
        cached = self.cache.get(key)
        translation = (
            str(cached.get("translation", "")).strip() if isinstance(cached, dict) else ""
        )
        if translation:
            try:
                self._validate_translation(translation, cues)
            except ValueError:
                translation = ""
        if not translation:
            translation = self._request(cues, context)
            self.cache.put(key, {"translation": translation})
        return translation

    def translate_batch(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
    ) -> list[SubtitleCue]:
        from .offline import split_group_translation

        translation = self.translate_paragraph(cues, context)
        parts = split_group_translation(
            translation,
            cues,
            source_code=self.source_code,
            target_code=self.target_code,
        )
        if parts is None:
            raise LocalizerError("Could not project the local AI paragraph onto cue timings.")
        return [cue.model_copy(update={"text": text}) for cue, text in zip(cues, parts, strict=True)]
