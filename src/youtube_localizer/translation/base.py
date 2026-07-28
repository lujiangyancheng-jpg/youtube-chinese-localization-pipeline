from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import SubtitleCue


@dataclass
class TranslationContext:
    title: str = ""
    channel: str = ""
    description: str = ""
    source_url: str = ""
    glossary: dict[str, str] = field(default_factory=dict)


class TranslationProvider(ABC):
    @abstractmethod
    def translate_batch(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
    ) -> list[SubtitleCue]:
        raise NotImplementedError
