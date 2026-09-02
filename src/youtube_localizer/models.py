from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SubtitleCue(BaseModel):
    id: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("end_ms")
    @classmethod
    def end_after_zero(cls, value: int) -> int:
        return value

    def validate_timing(self) -> None:
        if self.start_ms >= self.end_ms:
            raise ValueError(f"Cue {self.id}: start time must be before end time")


class SourceMetadata(BaseModel):
    source_type: str
    source_input: str
    source_url: str | None = None
    video_id: str
    title: str
    channel: str = ""
    duration: float = 0.0
    description: str = ""
    upload_date: str = ""
    language: str = ""
    thumbnail_url: str = ""
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    video_codec: str = ""
    audio_codec: str = ""
    pixel_format: str = ""
    color_space: str = ""
    color_transfer: str = ""
    color_primaries: str = ""
    variable_frame_rate: bool = False
    audio_streams: list[dict[str, Any]] = Field(default_factory=list)
    subtitle_language: str = ""
    subtitle_kind: str = ""
    english_subtitle_language: str = ""
    english_subtitle_kind: str = ""
    chinese_subtitle_language: str = ""
    chinese_subtitle_kind: str = ""


class OutputArtifact(BaseModel):
    """Compact integrity metadata for a completed pipeline output."""

    path: str
    size_bytes: int = Field(ge=0)
    fingerprint: str
    fingerprint_kind: str


class StepRecord(BaseModel):
    name: str
    status: str
    started_at: str
    ended_at: str | None = None
    input_hash: str
    config_hash: str
    output_files: list[str] = Field(default_factory=list)
    output_artifacts: list[OutputArtifact] = Field(default_factory=list)
    error_message: str | None = None
    retry_count: int = 0
    elapsed_seconds: float | None = None


class PipelineStateData(BaseModel):
    version: int = 2
    source_input: str = ""
    project_status: str = "incomplete"
    updated_at: str = ""
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def source(self) -> Path:
        return self.root / "source"

    @property
    def subtitles(self) -> Path:
        return self.root / "subtitles"

    @property
    def translation_chunks(self) -> Path:
        return self.subtitles / "translation_chunks"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def rendered(self) -> Path:
        return self.root / "rendered"

    @property
    def enhanced_source(self) -> Path:
        return self.rendered / "enhanced_source.mp4"

    @property
    def publishing(self) -> Path:
        return self.root / "publishing"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def metadata(self) -> Path:
        return self.source / "metadata.json"

    @property
    def english_srt(self) -> Path:
        return self.subtitles / "english.cleaned.srt"

    @property
    def chinese_srt(self) -> Path:
        return self.subtitles / "chinese.srt"

    @property
    def english_ass(self) -> Path:
        return self.subtitles / "english.ass"

    @property
    def chinese_ass(self) -> Path:
        return self.subtitles / "chinese.ass"

    @property
    def bilingual_srt(self) -> Path:
        return self.subtitles / "bilingual.srt"

    @property
    def bilingual_ass(self) -> Path:
        return self.subtitles / "bilingual.ass"

    @property
    def chinese_hardsub(self) -> Path:
        return self.rendered / "chinese_hardsub.mp4"

    @property
    def english_hardsub(self) -> Path:
        return self.rendered / "english_hardsub.mp4"

    @property
    def chinese_softsub(self) -> Path:
        return self.rendered / "chinese_softsub.mp4"

    @property
    def english_softsub(self) -> Path:
        return self.rendered / "english_softsub.mp4"

    def subtitle_srt(self, language_code: str) -> Path:
        """Return the stable subtitle path for a target language.

        Keep the legacy Chinese and English names so existing projects remain resumable.
        Other languages use their ISO code, for example ``subtitles/es.srt``.
        """
        if language_code == "en":
            return self.english_srt
        if language_code == "zh":
            return self.chinese_srt
        return self.subtitles / f"{language_code}.srt"

    def subtitle_ass(self, language_code: str) -> Path:
        if language_code == "en":
            return self.english_ass
        if language_code == "zh":
            return self.chinese_ass
        return self.subtitles / f"{language_code}.ass"

    def hardsub_output(self, language_code: str) -> Path:
        if language_code == "en":
            return self.english_hardsub
        if language_code == "zh":
            return self.chinese_hardsub
        return self.rendered / f"{language_code}_hardsub.mp4"

    def softsub_output(self, language_code: str) -> Path:
        if language_code == "en":
            return self.english_softsub
        if language_code == "zh":
            return self.chinese_softsub
        return self.rendered / f"{language_code}_softsub.mp4"

    @property
    def state_file(self) -> Path:
        return self.root / "pipeline_state.json"

    def create(self) -> None:
        for directory in (
            self.source,
            self.subtitles,
            self.translation_chunks,
            self.audio,
            self.rendered,
            self.publishing,
            self.logs,
            self.temp,
        ):
            directory.mkdir(parents=True, exist_ok=True)
