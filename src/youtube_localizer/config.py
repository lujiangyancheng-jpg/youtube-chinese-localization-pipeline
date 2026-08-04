from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ConfigurationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DownloadConfig(StrictModel):
    format: str = "bestvideo+bestaudio/best"
    format_sort: list[str] = Field(
        default_factory=lambda: ["res", "fps", "br", "size"], min_length=1
    )
    prefer_mp4: bool = True
    download_thumbnail: bool = True
    download_metadata: bool = True
    prefer_youtube_chinese: bool = True


class TranscriptionConfig(StrictModel):
    model: str = "medium"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: str = "auto"
    beam_size: int = Field(default=5, ge=1, le=20)
    vad_filter: bool = True
    word_timestamps: bool = True


class TranslationConfig(StrictModel):
    direction: Literal["en-to-zh", "zh-to-en"] = "en-to-zh"
    provider: Literal["manual", "offline", "ollama", "openai-compatible"] = "manual"
    model: str = ""
    endpoint: str = ""
    batch_size: int = Field(default=40, ge=1, le=200)
    preserve_timestamps: bool = True
    glossary_file: str = "glossary.yaml"
    offline_model_directory: Path = Path(
        "~/.youtube-chinese-localizer/models/translate-en_zh-1_9"
    )
    offline_model_url: str = (
        "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel"
    )
    offline_zh_en_model_directory: Path = Path(
        "~/.youtube-chinese-localizer/models/translate-zh_en-1_9"
    )
    offline_zh_en_model_url: str = (
        "https://argos-net.com/v1/translate-zh_en-1_9.argosmodel"
    )
    offline_device: Literal["auto", "cpu", "cuda"] = "auto"
    offline_compute_type: str = "auto"
    offline_auto_download: bool = True
    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_auto_pull: bool = True
    ollama_timeout_seconds: int = Field(default=600, ge=30, le=3600)


class SubtitleConfig(StrictModel):
    format: Literal["srt", "ass"] = "ass"
    font: str = "Microsoft YaHei"
    font_size: int = Field(default=48, ge=12, le=120)
    english_font_size: int = Field(default=34, ge=10, le=100)
    outline: int = Field(default=3, ge=0, le=10)
    shadow: int = Field(default=1, ge=0, le=10)
    margin_v: int = Field(default=45, ge=0, le=500)
    max_lines: int = Field(default=2, ge=1, le=4)
    max_chinese_chars_per_line: int = Field(default=20, ge=8, le=40)
    preserve_sound_descriptions: bool = True


class RenderConfig(StrictModel):
    codec: str = "libx264"
    crf: int = Field(default=18, ge=0, le=51)
    preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    faststart: bool = True
    copy_audio_when_possible: bool = True


class PublishingConfig(StrictModel):
    generate_metadata: bool = True
    attribution_template: str = (
        "原视频作者：{channel}\n"
        "原视频链接：{source_url}\n"
        "本视频经授权或依据相应许可进行翻译与转载。"
    )
    permission_note: str = "请在发布前填写实际授权或许可证信息。"


class AppConfig(StrictModel):
    output_directory: Path = Path("output")
    subtitle_language: str = "zh-CN"
    subtitle_mode: Literal["chinese", "bilingual_en_zh", "bilingual_zh_en"] = "chinese"
    download: DownloadConfig = DownloadConfig()
    transcription: TranscriptionConfig = TranscriptionConfig()
    translation: TranslationConfig = TranslationConfig()
    subtitles: SubtitleConfig = SubtitleConfig()
    render: RenderConfig = RenderConfig()
    publishing: PublishingConfig = PublishingConfig()


def load_config(path: Path | None = None) -> AppConfig:
    load_dotenv(override=False)
    data: dict = {}
    if path:
        if not path.is_file():
            raise ConfigurationError(f"Configuration file does not exist: {path}")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"Cannot read YAML configuration {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigurationError("The configuration root must be a YAML mapping.")
        data = loaded

    endpoint = os.getenv("OPENAI_COMPATIBLE_ENDPOINT")
    model = os.getenv("OPENAI_COMPATIBLE_MODEL")
    if endpoint or model:
        translation = dict(data.get("translation", {}))
        if endpoint:
            translation["endpoint"] = endpoint
        if model:
            translation["model"] = model
        data["translation"] = translation

    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration:\n{exc}") from exc
