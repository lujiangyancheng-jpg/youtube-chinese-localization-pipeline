from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import AppConfig, load_config
from .doctor import run_doctor
from .errors import LocalizerError
from .logging_config import configure_logging
from .models import ProjectPaths
from .pipeline import (
    _write_localized_subtitles,
    export_manual_translation,
    find_source_video,
    load_project_config,
    load_project_metadata,
    process_pipeline,
    render_project,
    save_project_config,
    translate_with_api,
)
from .publishing.metadata_generator import generate_publishing_assets
from .rendering.preview import render_preview
from .rendering.validation import validate_rendered_video
from .state import PipelineState
from .subtitles.normalize import validate_cues
from .subtitles.parser import parse_subtitle
from .transcription.audio import extract_transcription_audio
from .transcription.whisper_engine import transcribe_audio
from .translation.manual import import_translation_file
from .utils.files import ensure_within
from .utils.hashing import hash_file, stable_hash

app = typer.Typer(
    name="youtube-localizer",
    no_args_is_help=True,
    add_completion=False,
    help=(
        "Create Chinese localization assets from public, authorized YouTube videos or local "
        "video files. Do not use it for content you lack permission to translate/redistribute."
    ),
)
console = Console()
error_console = Console(stderr=True)

ConfigOption = Annotated[
    Path | None,
    typer.Option("--config", "-c", help="YAML configuration file.", exists=True, dir_okay=False),
]


def _project(path: Path) -> ProjectPaths:
    root = path.expanduser().resolve()
    if not root.is_dir() or not (root / "pipeline_state.json").is_file():
        raise LocalizerError(f"Not a localization project directory: {root}")
    return ProjectPaths(root)


def _configured(
    config_path: Path | None,
    *,
    output_dir: Path | None = None,
    subtitle_mode: str | None = None,
    translation_provider: str | None = None,
) -> AppConfig:
    config = load_config(config_path)
    changes = {}
    if output_dir:
        changes["output_directory"] = output_dir
    if subtitle_mode:
        if subtitle_mode not in {"chinese", "bilingual_en_zh", "bilingual_zh_en"}:
            raise LocalizerError(
                "--subtitle-mode must be chinese, bilingual_en_zh, or bilingual_zh_en."
            )
        changes["subtitle_mode"] = subtitle_mode
    if translation_provider:
        if translation_provider not in {"manual", "openai-compatible"}:
            raise LocalizerError("--translation-provider must be manual or openai-compatible.")
        changes["translation"] = config.translation.model_copy(
            update={"provider": translation_provider}
        )
    return config.model_copy(update=changes)


@app.command("process")
def process_command(
    input_value: Annotated[str, typer.Argument(help="Public YouTube URL or local video path.")],
    config_path: ConfigOption = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", "-o", help="Override output directory.")
    ] = None,
    subtitle_mode: Annotated[
        str | None,
        typer.Option(
            "--subtitle-mode",
            help="chinese, bilingual_en_zh, or bilingual_zh_en.",
        ),
    ] = None,
    translation_provider: Annotated[
        str | None,
        typer.Option(
            "--translation-provider",
            help="manual or openai-compatible.",
        ),
    ] = None,
    resume: Annotated[bool, typer.Option("--resume", help="Resume a matching project.")] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing matching project.")
    ] = False,
    force_step: Annotated[
        list[str] | None,
        typer.Option(
            "--force-step",
            help="Repeat one stage: acquire, english_subtitles, transcribe, translate, or render.",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run acquisition, English subtitles/transcription, translation, and rendering."""
    config = _configured(
        config_path,
        output_dir=output_dir,
        subtitle_mode=subtitle_mode,
        translation_provider=translation_provider,
    )
    console.print(
        "[yellow]Legal notice:[/] process only content you own, public-domain/CC content, or "
        "content you have explicit permission to translate and redistribute."
    )
    result = process_pipeline(
        input_value,
        config,
        resume=resume,
        overwrite=overwrite,
        force_steps=set(force_step or []),
        verbose=verbose,
    )
    console.print(f"[bold green]Project:[/] {result.project.root}")
    if result.status == "awaiting_manual_translation":
        console.print(
            "[bold yellow]English subtitles are ready.[/] Translate every Markdown chunk in "
            f"{result.project.translation_chunks}, then run `translate-import` for each response."
        )
        console.print(
            "ChatGPT Plus does not include OpenAI API credits; this manual workflow uses no API key."
        )
    else:
        console.print(
            f"[bold green]Completed:[/] {result.project.rendered / 'chinese_hardsub.mp4'}"
        )


@app.command("batch")
def batch_command(
    inputs_file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, help="UTF-8 file with one input per line."),
    ],
    config_path: ConfigOption = None,
    resume: Annotated[bool, typer.Option("--resume")] = False,
) -> None:
    """Process multiple URLs/local paths sequentially."""
    config = load_config(config_path)
    lines = [
        line.strip()
        for line in inputs_file.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise LocalizerError("The batch input file contains no usable inputs.")
    failures = 0
    for index, value in enumerate(lines, start=1):
        console.rule(f"[bold]Input {index}/{len(lines)}")
        try:
            result = process_pipeline(value, config, resume=resume)
            console.print(f"{result.status}: {result.project.root}")
        except LocalizerError as exc:
            failures += 1
            error_console.print(f"[red]Failed:[/] {value}\n{exc}")
    if failures:
        raise LocalizerError(f"{failures} of {len(lines)} batch inputs failed.")


@app.command("inspect")
def inspect_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
) -> None:
    """Show project metadata and resumable stage state."""
    project = _project(project_path)
    metadata = load_project_metadata(project)
    state = PipelineState(project.state_file)
    console.print(f"[bold]{metadata.title}[/]")
    console.print(f"Project: {project.root}")
    console.print(f"Source: {metadata.source_type} — {metadata.source_input}")
    console.print(f"Duration: {metadata.duration:.2f}s")
    console.print(f"Status: {state.data.project_status}")
    table = Table("Step", "Status", "Elapsed", "Retries", "Error")
    for name, record in state.data.steps.items():
        table.add_row(
            name,
            record.status,
            f"{record.elapsed_seconds:.3f}s" if record.elapsed_seconds is not None else "",
            str(record.retry_count),
            record.error_message or "",
        )
    console.print(table)


@app.command("transcribe")
def transcribe_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config_path: ConfigOption = None,
) -> None:
    """Force faster-whisper transcription for an existing project."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    source = find_source_video(project)
    configure_logging(project.logs / "pipeline.log")
    state = PipelineState(project.state_file)
    audio = project.audio / "transcription_audio.wav"
    raw_transcription = project.subtitles / "transcription.raw.json"
    with state.step(
        "english_subtitles",
        input_hash=hash_file(source),
        config_hash=stable_hash(config.transcription),
    ) as outputs:
        extract_transcription_audio(source, audio)
        cleanup = transcribe_audio(
            audio,
            raw_transcription,
            project.english_srt,
            config.transcription,
        )
        outputs.extend([audio, raw_transcription, project.english_srt])
    for stale in (
        project.chinese_srt,
        project.subtitles / "chinese.ass",
        project.bilingual_srt,
        project.bilingual_ass,
        project.temp / "manual_translations.json",
        project.rendered / "chinese_hardsub.mp4",
    ):
        stale.unlink(missing_ok=True)
    export_manual_translation(project, config)
    state.mark_status("awaiting_manual_translation")
    console.print(
        f"[green]Transcribed {len(cleanup.cues)} cues:[/] {project.english_srt}\n"
        f"Manual translation chunks: {project.translation_chunks}"
    )


@app.command("translate-export")
def translate_export_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config_path: ConfigOption = None,
) -> None:
    """Export numbered Markdown/JSONL chunks for manual ChatGPT translation."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    state = PipelineState(project.state_file)
    with state.step(
        "translation_export",
        input_hash=hash_file(project.english_srt),
        config_hash=stable_hash(config.translation),
    ) as outputs:
        exported = export_manual_translation(project, config)
        outputs.extend(exported)
        outputs.append(project.translation_chunks / "manifest.json")
    state.mark_status("awaiting_manual_translation")
    console.print(
        f"[green]Exported {len(exported)} chunks to:[/] {project.translation_chunks}\n"
        "Upload each chunk to ChatGPT and save the JSONL response. ChatGPT Plus does not "
        "include OpenAI API credits; this workflow needs no API key."
    )


@app.command("translate-import")
def translate_import_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    translated_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config_path: ConfigOption = None,
) -> None:
    """Validate and import a translated JSONL chunk without changing timestamps."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    state = PipelineState(project.state_file)
    with state.step(
        "translation_import",
        input_hash=hash_file(translated_file),
        config_hash=stable_hash(config.translation),
    ) as outputs:
        imported, total, warnings = import_translation_file(
            project,
            translated_file,
            width=config.subtitles.max_chinese_chars_per_line,
            max_lines=config.subtitles.max_lines,
            subtitle_mode=config.subtitle_mode,
            subtitle_config=config.subtitles,
        )
        outputs.append(project.temp / "manual_translations.json")
        if project.chinese_srt.is_file():
            english = parse_subtitle(project.english_srt)
            chinese = parse_subtitle(project.chinese_srt)
            localized, additional = _write_localized_subtitles(project, english, chinese, config)
            outputs.extend(localized)
            warnings.extend(additional)
            state.mark_status("translation_ready")
    console.print(f"[green]Imported translations:[/] {imported}/{total} cues")
    if imported == total:
        console.print(
            f"[bold green]Chinese subtitles are complete:[/] {project.chinese_srt}\n"
            f'Next: python main.py render "{project.root}"'
        )
    else:
        console.print(
            f"Import the remaining translated chunks ({total - imported} cues outstanding)."
        )
    for warning in warnings:
        console.print(f"[yellow]Warning:[/] {warning}")


@app.command("translate")
def translate_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config_path: ConfigOption = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="manual or openai-compatible.")
    ] = None,
) -> None:
    """Export manual chunks or run configured OpenAI-compatible translation."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    if provider:
        if provider not in {"manual", "openai-compatible"}:
            raise LocalizerError("--provider must be manual or openai-compatible.")
        config = config.model_copy(
            update={"translation": config.translation.model_copy(update={"provider": provider})}
        )
    save_project_config(project, config)
    if config.translation.provider == "manual":
        translate_export_command(project.root, config_path=None)
        return
    state = PipelineState(project.state_file)
    with state.step(
        "translate",
        input_hash=hash_file(project.english_srt),
        config_hash=stable_hash(config.translation),
    ) as step_outputs:
        outputs, warnings = translate_with_api(project, config)
        step_outputs.extend(outputs)
    state.mark_status("translation_ready")
    console.print(f"[green]Translation complete:[/] {', '.join(str(path) for path in outputs)}")
    for warning in warnings:
        console.print(f"[yellow]Warning:[/] {warning}")


@app.command("render")
def render_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config_path: ConfigOption = None,
) -> None:
    """Render and validate the final hard-subtitled MP4."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    state = PipelineState(project.state_file)
    source = find_source_video(project)
    subtitle = (
        project.subtitles / "chinese.ass"
        if config.subtitle_mode == "chinese"
        else project.bilingual_ass
    )
    with state.step(
        "render",
        input_hash=stable_hash(
            {
                "source": hash_file(source),
                "subtitle": hash_file(subtitle) if subtitle.is_file() else "",
            }
        ),
        config_hash=stable_hash(config.render),
    ) as outputs:
        output = render_project(project, config)
        outputs.append(output)
    state.mark_status("completed")
    console.print(f"[bold green]Rendered and validated:[/] {output}")


@app.command("preview")
def preview_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    start: Annotated[float, typer.Option("--start", min=0)] = 0,
    duration: Annotated[float, typer.Option("--duration", min=0.1)] = 15,
    config_path: ConfigOption = None,
) -> None:
    """Render a short styled subtitle preview clip."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    metadata = load_project_metadata(project)
    subtitle = (
        project.subtitles / "chinese.ass"
        if config.subtitle_mode == "chinese"
        else project.bilingual_ass
    )
    if not subtitle.is_file():
        raise LocalizerError("Styled subtitles are not ready. Import/translate subtitles first.")
    output = project.rendered / f"preview_{start:g}_{duration:g}.mp4"
    render_preview(
        find_source_video(project),
        subtitle,
        output,
        config.render,
        source_audio_codec=metadata.audio_codec,
        start=start,
        duration=duration,
    )
    console.print(f"[green]Preview created:[/] {output}")


@app.command("metadata")
def metadata_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config_path: ConfigOption = None,
) -> None:
    """Generate conservative publishing metadata drafts for human review."""
    project = _project(project_path)
    config = load_config(config_path) if config_path else load_project_config(project)
    outputs = generate_publishing_assets(
        load_project_metadata(project), project.publishing, config.publishing
    )
    console.print(
        f"[green]Publishing drafts created:[/] {project.publishing}\n"
        "The title and permission/license fields are intentionally marked for human review."
    )
    for output in outputs:
        console.print(f"- {output.name}")


@app.command("validate")
def validate_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    decode: Annotated[bool, typer.Option("--decode/--no-decode")] = True,
) -> None:
    """Validate subtitle timing and any rendered MP4."""
    project = _project(project_path)
    metadata = load_project_metadata(project)
    checked = 0
    for subtitle in (
        project.english_srt,
        project.chinese_srt,
        project.bilingual_srt,
    ):
        if subtitle.is_file():
            errors = validate_cues(parse_subtitle(subtitle))
            if errors:
                raise LocalizerError(f"{subtitle.name} is invalid:\n" + "\n".join(errors))
            console.print(f"[green]Valid:[/] {subtitle}")
            checked += 1
    rendered = project.rendered / "chinese_hardsub.mp4"
    if rendered.is_file():
        validate_rendered_video(rendered, expected_duration=metadata.duration, decode=decode)
        console.print(f"[green]Valid and decodable:[/] {rendered}")
        checked += 1
    if not checked:
        raise LocalizerError("No subtitle or rendered output files exist yet.")


@app.command("clean")
def clean_command(
    project_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Remove only temporary/cache/partial files; preserve sources and final assets."""
    project = _project(project_path)
    if not yes and not typer.confirm(
        f"Remove temporary/cache files under {project.root}? Final outputs will be preserved."
    ):
        raise typer.Abort()
    temp = ensure_within(project.temp, project.root)
    if temp.is_dir():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    removed_partials = 0
    for partial in project.root.rglob("*.partial.*"):
        ensure_within(partial, project.root).unlink(missing_ok=True)
        removed_partials += 1
    console.print(
        f"[green]Cleaned:[/] temporary cache and {removed_partials} partial file(s). "
        "Source and final assets were preserved."
    )


@app.command("doctor")
def doctor_command(
    config_path: ConfigOption = None,
) -> None:
    """Check Python, FFmpeg, yt-dlp, Whisper/CUDA, fonts, and output access."""
    config = load_config(config_path)
    checks = run_doctor(config.output_directory.expanduser())
    table = Table("Check", "Status", "Details")
    styles = {"ok": "green", "missing": "red", "warning": "yellow", "optional": "cyan"}
    for check in checks:
        table.add_row(check.name, f"[{styles[check.status]}]{check.status}[/]", check.detail)
    console.print(table)
    missing = [check for check in checks if check.required and check.status != "ok"]
    if missing:
        error_console.print(
            "[red]Required dependencies are missing.[/] See README.md for Windows setup."
        )
        raise typer.Exit(1)


@app.command("version")
def version_command() -> None:
    """Print the application version."""
    console.print(__version__)


@app.command("gui")
def gui_command() -> None:
    """Open the local paste-a-link desktop interface."""
    from .gui import run_gui

    run_gui()


KNOWN_COMMANDS = {
    "process",
    "batch",
    "inspect",
    "transcribe",
    "translate",
    "translate-export",
    "translate-import",
    "render",
    "preview",
    "metadata",
    "validate",
    "clean",
    "doctor",
    "gui",
    "version",
}


def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if argv[0] == "--batch":
        return ["batch", *argv[1:]]
    if argv[0] not in KNOWN_COMMANDS and not argv[0].startswith("-"):
        return ["process", *argv]
    return argv


def run() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    configure_logging()
    argv = normalize_argv(sys.argv[1:])
    try:
        result = app(args=argv, prog_name=Path(sys.argv[0]).name, standalone_mode=False)
        if isinstance(result, int) and result:
            raise SystemExit(result)
    except LocalizerError as exc:
        error_console.print(f"[bold red]Error:[/] {exc}")
        raise SystemExit(1) from None
    except typer.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except Exception as exc:
        show = getattr(exc, "show", None)
        exit_code = getattr(exc, "exit_code", None)
        if callable(show) and isinstance(exit_code, int):
            show(file=error_console.file)
            raise SystemExit(exit_code) from None
        raise
