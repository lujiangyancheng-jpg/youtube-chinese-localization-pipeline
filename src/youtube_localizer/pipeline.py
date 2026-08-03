from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from .config import AppConfig
from .download.local import import_local, inspect_local
from .download.youtube import (
    download_youtube,
    inspect_youtube,
    is_youtube_url,
    save_raw_metadata,
    save_thumbnail,
    youtube_video_id,
)
from .errors import InputValidationError, LocalizerError, ProjectExistsError
from .logging_config import configure_logging
from .models import ProjectPaths, SourceMetadata, SubtitleCue
from .publishing.metadata_generator import generate_publishing_assets
from .rendering.ffmpeg import render_hardsub
from .rendering.validation import validate_rendered_video
from .reporting import build_report, write_report
from .state import PipelineState
from .subtitles.bilingual import combine_bilingual
from .subtitles.cleanup import cleanup_english
from .subtitles.normalize import normalize_cues, validate_cues
from .subtitles.parser import parse_subtitle, write_srt
from .subtitles.readability import readability_pass
from .subtitles.styling import write_ass
from .transcription.audio import extract_transcription_audio
from .transcription.whisper_engine import transcribe_audio
from .translation.base import TranslationContext
from .translation.cache import TranslationCache
from .translation.glossary import load_glossary
from .translation.manual import ManualExportProvider
from .translation.offline import LocalOfflineProvider
from .translation.openai_compatible import OpenAICompatibleProvider
from .utils.files import (
    atomic_write_json,
    available_bytes,
    load_json,
    remove_project,
    sanitize_filename,
)
from .utils.hashing import hash_file, hash_text, stable_hash

LOGGER = logging.getLogger(__name__)
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}


@dataclass
class PipelineResult:
    project: ProjectPaths
    status: str
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def find_source_video(project: ProjectPaths) -> Path:
    candidates = [
        path
        for path in project.source.glob("source_video.*")
        if path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not candidates:
        raise LocalizerError(f"No imported/downloaded source video exists in {project.source}")
    return max(candidates, key=lambda path: path.stat().st_size)


def load_project_metadata(project: ProjectPaths) -> SourceMetadata:
    if not project.metadata.is_file():
        raise LocalizerError(f"Project metadata is missing: {project.metadata}")
    return SourceMetadata.model_validate(load_json(project.metadata))


def save_project_config(project: ProjectPaths, config: AppConfig) -> Path:
    path = project.root / "config.resolved.json"
    atomic_write_json(path, config.model_dump(mode="json"))
    return path


def load_project_config(project: ProjectPaths) -> AppConfig:
    path = project.root / "config.resolved.json"
    if path.is_file():
        return AppConfig.model_validate(load_json(path))
    return AppConfig()


def _source_identifier(value: str) -> str:
    video_id = youtube_video_id(value)
    if video_id:
        return video_id
    path = Path(value).expanduser().resolve()
    return hash_text(str(path).casefold())[:10]


def _find_existing_project(output_root: Path, identifier: str) -> Path | None:
    if not output_root.is_dir():
        return None
    matches = [
        path
        for path in output_root.iterdir()
        if path.is_dir() and path.name.endswith(f"_{identifier}")
    ]
    if len(matches) > 1:
        raise LocalizerError(
            f"Multiple projects end with identifier {identifier}: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0] if matches else None


def _inspect_input(value: str) -> tuple[SourceMetadata, dict[str, Any] | None]:
    if is_youtube_url(value):
        return inspect_youtube(value)
    if value.lower().startswith(("http://", "https://")):
        raise InputValidationError(
            "Only public YouTube URLs are supported. Other remote URLs are not downloaded."
        )
    metadata = inspect_local(Path(value))
    return metadata, None


def prepare_project(
    value: str,
    config: AppConfig,
    *,
    resume: bool = False,
    overwrite: bool = False,
) -> tuple[ProjectPaths, SourceMetadata, dict[str, Any] | None]:
    if resume and overwrite:
        raise InputValidationError("--resume and --overwrite cannot be used together.")
    output_root = config.output_directory.expanduser().resolve()
    identifier = _source_identifier(value)
    existing = _find_existing_project(output_root, identifier)
    if existing and resume:
        project = ProjectPaths(existing)
        project.create()
        metadata = load_project_metadata(project)
        return project, metadata, None

    metadata, raw_info = _inspect_input(value)
    name = f"{sanitize_filename(metadata.title, max_length=80)}_{metadata.video_id}"
    root = output_root / name
    if root.exists():
        if overwrite:
            remove_project(root, output_root)
        else:
            raise ProjectExistsError(
                f"Project already exists: {root}. Use --resume to continue it or --overwrite "
                "to replace it."
            )
    project = ProjectPaths(root)
    project.create()
    atomic_write_json(project.metadata, metadata.model_dump(mode="json"))
    save_project_config(project, config)
    return project, metadata, raw_info


def _input_hash(metadata: SourceMetadata, fallback_video: Path | None = None) -> str:
    if metadata.source_type == "local":
        path = Path(metadata.source_input)
        if path.is_file():
            return hash_file(path)
        if fallback_video and fallback_video.is_file():
            LOGGER.warning(
                "The original local file is no longer available; resuming from the safe "
                "project copy."
            )
            return hash_file(fallback_video)
        raise InputValidationError(f"Original local source no longer exists: {path}")
    return stable_hash(
        {
            "source_url": metadata.source_url or metadata.source_input,
            "video_id": metadata.video_id,
        }
    )


def _translation_context(metadata: SourceMetadata, glossary: dict[str, str]) -> TranslationContext:
    return TranslationContext(
        title=metadata.title,
        channel=metadata.channel,
        description=metadata.description,
        source_url=metadata.source_url or metadata.source_input,
        glossary=glossary,
    )


def _write_localized_subtitles(
    project: ProjectPaths,
    english: list[SubtitleCue],
    chinese: list[SubtitleCue],
    config: AppConfig,
) -> tuple[list[Path], list[str]]:
    readable, issues = readability_pass(
        chinese,
        width=config.subtitles.max_chinese_chars_per_line,
        max_lines=config.subtitles.max_lines,
    )
    write_srt(project.chinese_srt, readable)
    chinese_ass = project.subtitles / "chinese.ass"
    write_ass(chinese_ass, readable, config.subtitles)
    outputs = [project.chinese_srt, chinese_ass]
    if config.subtitle_mode != "chinese":
        bilingual = combine_bilingual(english, readable, mode=config.subtitle_mode)
        write_srt(project.bilingual_srt, bilingual)
        write_ass(
            project.bilingual_ass,
            bilingual,
            config.subtitles,
            bilingual_mode=config.subtitle_mode,
        )
        outputs.extend([project.bilingual_srt, project.bilingual_ass])
    warnings = [f"Cue {issue.cue_id}: {issue.message}" for issue in issues]
    return outputs, warnings


def export_manual_translation(
    project: ProjectPaths,
    config: AppConfig,
    metadata: SourceMetadata | None = None,
) -> list[Path]:
    metadata = metadata or load_project_metadata(project)
    english = parse_subtitle(project.english_srt)
    glossary_path = Path(config.translation.glossary_file)
    if not glossary_path.is_absolute():
        candidates = [project.root / glossary_path, Path.cwd() / glossary_path]
        glossary_path = next((path for path in candidates if path.is_file()), candidates[0])
    glossary = load_glossary(glossary_path)
    provider = ManualExportProvider()
    return provider.export(
        english,
        _translation_context(metadata, glossary),
        project.translation_chunks,
        batch_size=config.translation.batch_size,
    )


def translate_with_api(
    project: ProjectPaths,
    config: AppConfig,
    metadata: SourceMetadata | None = None,
) -> tuple[list[Path], list[str]]:
    metadata = metadata or load_project_metadata(project)
    english = parse_subtitle(project.english_srt)
    glossary_path = Path(config.translation.glossary_file)
    if not glossary_path.is_absolute():
        glossary_path = project.root / glossary_path
    glossary = load_glossary(glossary_path)
    provider = OpenAICompatibleProvider(
        endpoint=config.translation.endpoint,
        model=config.translation.model,
        cache=TranslationCache(project.temp / "translation_cache"),
    )
    translated: list[SubtitleCue] = []
    batch_size = config.translation.batch_size
    base_context = _translation_context(metadata, glossary)
    for offset in range(0, len(english), batch_size):
        batch = english[offset : offset + batch_size]
        nearby = " ".join(cue.text for cue in english[max(0, offset - 3) : offset])
        batch_context = TranslationContext(
            title=base_context.title,
            channel=base_context.channel,
            description=(
                base_context.description
                + (f"\nNearby preceding subtitle context: {nearby}" if nearby else "")
            ),
            source_url=base_context.source_url,
            glossary=base_context.glossary,
        )
        translated.extend(provider.translate_batch(batch, batch_context))
    return _write_localized_subtitles(project, english, translated, config)


def translate_with_offline(
    project: ProjectPaths,
    config: AppConfig,
    metadata: SourceMetadata | None = None,
) -> tuple[list[Path], list[str]]:
    metadata = metadata or load_project_metadata(project)
    english = parse_subtitle(project.english_srt)
    glossary_path = Path(config.translation.glossary_file)
    if not glossary_path.is_absolute():
        candidates = [project.root / glossary_path, Path.cwd() / glossary_path]
        glossary_path = next((path for path in candidates if path.is_file()), candidates[0])
    glossary = load_glossary(glossary_path)
    model_directory = config.translation.offline_model_directory.expanduser()
    if not model_directory.is_absolute():
        model_directory = (Path.cwd() / model_directory).resolve()
    provider = LocalOfflineProvider(
        model_directory=model_directory,
        model_url=config.translation.offline_model_url,
        auto_download=config.translation.offline_auto_download,
        device=config.translation.offline_device,
        compute_type=config.translation.offline_compute_type,
        cache=TranslationCache(project.temp / "translation_cache"),
    )
    translated: list[SubtitleCue] = []
    batch_size = config.translation.batch_size
    context = _translation_context(metadata, glossary)
    for offset in range(0, len(english), batch_size):
        batch = english[offset : offset + batch_size]
        LOGGER.info(
            "Offline translating subtitle batch %s/%s…",
            offset // batch_size + 1,
            (len(english) + batch_size - 1) // batch_size,
        )
        translated.extend(provider.translate_batch(batch, context))
    return _write_localized_subtitles(project, english, translated, config)


def render_project(project: ProjectPaths, config: AppConfig) -> Path:
    metadata = load_project_metadata(project)
    source = find_source_video(project)
    if config.subtitle_mode == "chinese":
        subtitle = project.subtitles / "chinese.ass"
        if not subtitle.is_file():
            chinese = parse_subtitle(project.chinese_srt)
            write_ass(subtitle, chinese, config.subtitles)
    else:
        subtitle = project.bilingual_ass
        if not subtitle.is_file():
            english = parse_subtitle(project.english_srt)
            chinese = parse_subtitle(project.chinese_srt)
            bilingual = combine_bilingual(english, chinese, mode=config.subtitle_mode)
            write_ass(
                subtitle,
                bilingual,
                config.subtitles,
                bilingual_mode=config.subtitle_mode,
            )
    output = project.rendered / "chinese_hardsub.mp4"
    render_hardsub(
        source,
        subtitle,
        output,
        config.render,
        source_audio_codec=metadata.audio_codec,
    )
    validate_rendered_video(output, expected_duration=metadata.duration)
    return output


def process_pipeline(
    value: str,
    config: AppConfig,
    *,
    resume: bool = False,
    overwrite: bool = False,
    force_steps: set[str] | None = None,
    verbose: bool = False,
) -> PipelineResult:
    force_steps = force_steps or set()
    project, metadata, raw_info = prepare_project(value, config, resume=resume, overwrite=overwrite)
    configure_logging(project.logs / "pipeline.log", verbose=verbose)
    state = PipelineState(project.state_file, source_input=value)
    warnings: list[str] = []
    outputs: list[Path] = []
    cue_count = 0
    flagged_cues: list[int] = []
    subtitle_source = metadata.subtitle_kind
    started = monotonic()

    try:
        existing_video: Path | None
        try:
            existing_video = find_source_video(project)
        except LocalizerError:
            existing_video = None
        source_hash = _input_hash(metadata, existing_video)
        acquire_config_hash = stable_hash(config.download)
        acquire_outputs = [project.metadata] + ([existing_video] if existing_video else [])
        if not state.can_skip(
            "acquire",
            input_hash=source_hash,
            config_hash=acquire_config_hash,
            output_files=acquire_outputs,
            force="acquire" in force_steps,
        ):
            with state.step(
                "acquire", input_hash=source_hash, config_hash=acquire_config_hash
            ) as step_outputs:
                free = available_bytes(project.root)
                if metadata.source_type == "local":
                    original = Path(metadata.source_input)
                    if free < original.stat().st_size * 1.1:
                        raise LocalizerError(
                            "Insufficient free disk space to safely copy the local source video."
                        )
                    source_video = import_local(original, project.source)
                else:
                    if raw_info is None:
                        refreshed, raw_info = inspect_youtube(metadata.source_input)
                        metadata = refreshed
                    download = download_youtube(
                        metadata.source_url or metadata.source_input,
                        raw_info,
                        project.source,
                        config.download,
                    )
                    source_video = download.video
                    metadata.english_subtitle_language = download.english_language
                    metadata.english_subtitle_kind = download.english_kind
                    metadata.chinese_subtitle_language = download.chinese_language
                    metadata.chinese_subtitle_kind = download.chinese_kind
                    if download.chinese_subtitle:
                        metadata.subtitle_language = download.chinese_language
                        metadata.subtitle_kind = f"{download.chinese_kind} Chinese subtitles"
                    else:
                        metadata.subtitle_language = download.english_language
                        metadata.subtitle_kind = download.english_kind
                    subtitle_source = metadata.subtitle_kind
                    for subtitle_file in (
                        download.english_subtitle,
                        download.chinese_subtitle,
                    ):
                        if subtitle_file:
                            normalized_subtitle_location = project.subtitles / subtitle_file.name
                            subtitle_file.replace(normalized_subtitle_location)
                            step_outputs.append(normalized_subtitle_location)
                    if config.download.download_metadata:
                        raw_path = project.source / "metadata.raw.json"
                        save_raw_metadata(raw_info, raw_path)
                        step_outputs.append(raw_path)
                    if config.download.download_thumbnail and metadata.thumbnail_url:
                        thumbnail = project.source / "thumbnail.jpg"
                        save_thumbnail(metadata.thumbnail_url, thumbnail)
                        if thumbnail.is_file():
                            step_outputs.append(thumbnail)
                atomic_write_json(project.metadata, metadata.model_dump(mode="json"))
                step_outputs.extend([source_video, project.metadata])
        source_video = find_source_video(project)

        source_subtitles = sorted(
            [
                *project.subtitles.glob("source.en.vtt"),
                *project.subtitles.glob("source.en.srt"),
                *project.subtitles.glob("source.en.ass"),
                *project.source.glob("source.en.vtt"),
                *project.source.glob("source.en.srt"),
                *project.source.glob("source.en.ass"),
            ]
        )
        source_chinese_subtitles = sorted(
            [
                *project.subtitles.glob("source.zh.vtt"),
                *project.subtitles.glob("source.zh.srt"),
                *project.subtitles.glob("source.zh.ass"),
                *project.source.glob("source.zh.vtt"),
                *project.source.glob("source.zh.srt"),
                *project.source.glob("source.zh.ass"),
            ]
        )
        use_provided_chinese = bool(
            config.download.prefer_youtube_chinese
            and source_chinese_subtitles
            and "translate" not in force_steps
        )
        if use_provided_chinese:
            chinese_source = source_chinese_subtitles[0]
            chinese_source_hash = hash_file(chinese_source)
            chinese_config_hash = stable_hash(
                {
                    "preserve_sound_descriptions": config.subtitles.preserve_sound_descriptions,
                    "source_language": metadata.chinese_subtitle_language,
                }
            )
            if not state.can_skip(
                "youtube_chinese_subtitles",
                input_hash=chinese_source_hash,
                config_hash=chinese_config_hash,
                output_files=[project.chinese_srt],
            ):
                with state.step(
                    "youtube_chinese_subtitles",
                    input_hash=chinese_source_hash,
                    config_hash=chinese_config_hash,
                ) as step_outputs:
                    normalized_chinese = normalize_cues(
                        parse_subtitle(chinese_source),
                        preserve_sound_descriptions=config.subtitles.preserve_sound_descriptions,
                    )
                    errors = validate_cues(normalized_chinese)
                    if errors:
                        raise LocalizerError(
                            "Downloaded Chinese subtitle normalization failed:\n"
                            + "\n".join(errors)
                        )
                    write_srt(project.chinese_srt, normalized_chinese)
                    step_outputs.append(project.chinese_srt)
            subtitle_source = metadata.subtitle_kind or "YouTube Simplified Chinese subtitles"

        needs_english = (
            not use_provided_chinese
            or config.subtitle_mode != "chinese"
            or "translate" in force_steps
        )
        english_changed = False
        if needs_english:
            english_hash_source = (
                hash_file(source_subtitles[0]) if source_subtitles else hash_file(source_video)
            )
            subtitle_config_hash = stable_hash(
                {
                    "preserve_sound_descriptions": config.subtitles.preserve_sound_descriptions,
                    "transcription": config.transcription,
                }
            )
            english_changed = not state.can_skip(
                "english_subtitles",
                input_hash=english_hash_source,
                config_hash=subtitle_config_hash,
                output_files=[project.english_srt],
                force="english_subtitles" in force_steps or "transcribe" in force_steps,
            )
            if english_changed:
                with state.step(
                    "english_subtitles",
                    input_hash=english_hash_source,
                    config_hash=subtitle_config_hash,
                ) as step_outputs:
                    if source_subtitles and "transcribe" not in force_steps:
                        parsed = parse_subtitle(source_subtitles[0])
                        normalized = normalize_cues(
                            parsed,
                            preserve_sound_descriptions=config.subtitles.preserve_sound_descriptions,
                        )
                        errors = validate_cues(normalized)
                        if errors:
                            raise LocalizerError(
                                "Downloaded subtitle normalization failed:\n" + "\n".join(errors)
                            )
                        cleanup = cleanup_english(normalized)
                        write_srt(project.english_srt, cleanup.cues)
                        warnings.extend(cleanup.warnings)
                        flagged_cues.extend(cleanup.flagged_cue_ids)
                        if not use_provided_chinese:
                            subtitle_source = (
                                metadata.english_subtitle_kind
                                or metadata.subtitle_kind
                                or "downloaded English subtitles"
                            )
                        step_outputs.append(project.english_srt)
                    else:
                        audio = project.audio / "transcription_audio.wav"
                        extract_transcription_audio(source_video, audio)
                        raw_transcription = project.subtitles / "transcription.raw.json"
                        cleanup = transcribe_audio(
                            audio,
                            raw_transcription,
                            project.english_srt,
                            config.transcription,
                        )
                        warnings.extend(cleanup.warnings)
                        flagged_cues.extend(cleanup.flagged_cue_ids)
                        if not use_provided_chinese:
                            subtitle_source = "faster-whisper"
                        step_outputs.extend([audio, raw_transcription, project.english_srt])

        if english_changed:
            stale_files = [
                project.subtitles / "chinese.ass",
                project.bilingual_srt,
                project.bilingual_ass,
                project.temp / "manual_translations.json",
                project.rendered / "chinese_hardsub.mp4",
            ]
            if not use_provided_chinese:
                stale_files.append(project.chinese_srt)
            for stale in stale_files:
                stale.unlink(missing_ok=True)

        english = parse_subtitle(project.english_srt) if needs_english else []
        chinese = parse_subtitle(project.chinese_srt) if use_provided_chinese else []
        cue_count = len(chinese) if chinese else len(english)

        translation_hash = (
            hash_file(project.chinese_srt)
            if use_provided_chinese
            else hash_file(project.english_srt)
        )
        translation_config_hash = stable_hash(
            {
                "translation": config.translation,
                "subtitle_mode": config.subtitle_mode,
                "subtitles": config.subtitles,
            }
        )
        translation_current = state.can_skip(
            "translate",
            input_hash=translation_hash,
            config_hash=translation_config_hash,
            output_files=[project.chinese_srt],
            force="translate" in force_steps,
        )
        needs_translation = not use_provided_chinese and not project.chinese_srt.is_file()
        if not use_provided_chinese and config.translation.provider != "manual":
            needs_translation = not translation_current
        elif "translate" in force_steps:
            needs_translation = True

        if needs_translation:
            if config.translation.provider == "manual":
                if "translate" in force_steps:
                    for stale in (
                        project.chinese_srt,
                        project.subtitles / "chinese.ass",
                        project.bilingual_srt,
                        project.bilingual_ass,
                        project.temp / "manual_translations.json",
                        project.rendered / "chinese_hardsub.mp4",
                    ):
                        stale.unlink(missing_ok=True)
                manifest = project.translation_chunks / "manifest.json"
                if not state.can_skip(
                    "translation_export",
                    input_hash=translation_hash,
                    config_hash=translation_config_hash,
                    output_files=[manifest],
                    force="translate" in force_steps,
                ):
                    with state.step(
                        "translation_export",
                        input_hash=translation_hash,
                        config_hash=translation_config_hash,
                    ) as step_outputs:
                        step_outputs.extend(export_manual_translation(project, config, metadata))
                        step_outputs.append(manifest)
                state.mark_status("awaiting_manual_translation")
                outputs.extend([project.english_srt, manifest])
                report = build_report(
                    metadata,
                    state.data,
                    subtitle_source=subtitle_source,
                    whisper_model=(
                        config.transcription.model if subtitle_source == "faster-whisper" else ""
                    ),
                    translation_provider="manual",
                    cue_count=cue_count,
                    flagged_cues=flagged_cues,
                    output_paths=outputs,
                    warnings=warnings
                    + [
                        "Translation chunks are ready. Translate and import every chunk, then run "
                        "render or process --resume."
                    ],
                )
                write_report(project.logs, report)
                return PipelineResult(
                    project,
                    "awaiting_manual_translation",
                    outputs,
                    report["warnings"],
                )
            with state.step(
                "translate",
                input_hash=translation_hash,
                config_hash=translation_config_hash,
            ) as step_outputs:
                if config.translation.provider == "offline":
                    translated_outputs, translation_warnings = translate_with_offline(
                        project, config, metadata
                    )
                else:
                    translated_outputs, translation_warnings = translate_with_api(
                        project, config, metadata
                    )
                step_outputs.extend(translated_outputs)
                warnings.extend(translation_warnings)

        localized_outputs, localized_warnings = _write_localized_subtitles(
            project,
            english,
            parse_subtitle(project.chinese_srt),
            config,
        )
        outputs.extend(localized_outputs)
        warnings.extend(localized_warnings)

        if config.publishing.generate_metadata:
            metadata_outputs = generate_publishing_assets(
                metadata, project.publishing, config.publishing
            )
            outputs.extend(metadata_outputs)

        render_hash = stable_hash(
            {
                "video": hash_file(source_video),
                "subtitles": hash_file(
                    project.subtitles
                    / ("chinese.ass" if config.subtitle_mode == "chinese" else "bilingual.ass")
                ),
            }
        )
        render_config_hash = stable_hash(config.render)
        rendered = project.rendered / "chinese_hardsub.mp4"
        if not state.can_skip(
            "render",
            input_hash=render_hash,
            config_hash=render_config_hash,
            output_files=[rendered],
            force="render" in force_steps,
        ):
            with state.step(
                "render", input_hash=render_hash, config_hash=render_config_hash
            ) as step_outputs:
                step_outputs.append(render_project(project, config))
        outputs.append(rendered)
        state.mark_status("completed")
        report = build_report(
            metadata,
            state.data,
            subtitle_source=subtitle_source,
            whisper_model=config.transcription.model if subtitle_source == "faster-whisper" else "",
            translation_provider=(
                "youtube-provided" if use_provided_chinese else config.translation.provider
            ),
            cue_count=cue_count,
            flagged_cues=flagged_cues,
            render_parameters=config.render.model_dump(mode="json"),
            output_paths=outputs,
            warnings=warnings,
        )
        report["total_elapsed_seconds"] = round(monotonic() - started, 3)
        write_report(project.logs, report)
        return PipelineResult(project, "completed", outputs, warnings)
    except BaseException as exc:
        state.mark_status("failed")
        report = build_report(
            metadata,
            state.data,
            subtitle_source=subtitle_source,
            whisper_model=config.transcription.model if subtitle_source == "faster-whisper" else "",
            translation_provider=config.translation.provider,
            cue_count=cue_count,
            flagged_cues=flagged_cues,
            output_paths=outputs,
            warnings=warnings,
            errors=[str(exc)],
        )
        report["total_elapsed_seconds"] = round(monotonic() - started, 3)
        write_report(project.logs, report)
        LOGGER.exception("Pipeline failed")
        raise
