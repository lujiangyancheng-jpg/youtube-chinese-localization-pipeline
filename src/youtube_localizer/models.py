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
    audio_streams: list[dict[str, Any]] = Field(default_factory=list)
    subtitle_language: str = ""
    subtitle_kind: str = ""


class StepRecord(BaseModel):
    name: str
    status: str
    started_at: str
    ended_at: str | None = None
    input_hash: str
    config_hash: str
    output_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    retry_count: int = 0
    elapsed_seconds: float | None = None


class PipelineStateData(BaseModel):
    version: int = 1
    source_input: str = ""
    project_status: str = "incomplete"
    updated_at: str = ""
    steps: dict[str, StepRecord] = Field(default_factory=dict)


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
    def bilingual_srt(self) -> Path:
        return self.subtitles / "bilingual.srt"

    @property
    def bilingual_ass(self) -> Path:
        return self.subtitles / "bilingual.ass"

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
