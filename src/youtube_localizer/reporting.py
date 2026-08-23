from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import PipelineStateData, SourceMetadata
from .utils.files import atomic_write_json, atomic_write_text, load_json


def _performance_summary(state: PipelineStateData) -> dict[str, Any]:
    timings = {
        name: record.elapsed_seconds
        for name, record in state.steps.items()
        if record.elapsed_seconds is not None
    }
    if not timings:
        return {}
    slowest_stage, slowest_seconds = max(timings.items(), key=lambda item: item[1])
    recommendations = {
        "acquire": "下载最慢：确认网络和输出目录不在 OneDrive；高画质流会并行下载分片。",
        "english_subtitles": "识别最慢：运行 doctor 确认 CUDA 已用于 Whisper。",
        "chinese_subtitles": "识别最慢：运行 doctor 确认 CUDA 已用于 Whisper。",
        "translate": "翻译最慢：本地 AI 会保持段落上下文；后续运行会复用已缓存的段落。",
        "render": "压制最慢：运行 doctor 检查 NVENC；不可用时更新 NVIDIA 驱动以启用显卡编码。",
    }
    return {
        "slowest_stage": slowest_stage,
        "slowest_stage_seconds": slowest_seconds,
        "recommendation": recommendations.get(slowest_stage, "查看各阶段耗时后再调整设置。"),
    }


def load_report_context(logs_dir: Path) -> tuple[list[str], list[Path]]:
    """Load warnings and still-existing outputs from the most recent project report.

    Standalone commands such as ``render`` replace the report after completing a later stage.
    Keeping this context prevents earlier acquisition/transcription warnings from disappearing.
    """
    path = logs_dir / "report.json"
    if not path.is_file():
        return [], []
    try:
        report = load_json(path)
    except (OSError, TypeError, ValueError):
        return [], []
    if not isinstance(report, dict):
        return [], []
    raw_warnings = report.get("warnings", [])
    warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
    raw_outputs = report.get("output_paths", [])
    outputs: list[Path] = []
    if isinstance(raw_outputs, list):
        for item in raw_outputs:
            if not isinstance(item, str):
                continue
            candidate = Path(item)
            if candidate.exists() and candidate not in outputs:
                outputs.append(candidate)
    return list(dict.fromkeys(warnings)), outputs


def build_report(
    metadata: SourceMetadata,
    state: PipelineStateData,
    *,
    subtitle_source: str = "",
    whisper_model: str = "",
    translation_provider: str = "",
    cue_count: int = 0,
    flagged_cues: list[int] | None = None,
    render_parameters: dict[str, Any] | None = None,
    subtitle_quality: dict[str, Any] | None = None,
    output_paths: list[Path] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    stage_timings = {name: record.elapsed_seconds for name, record in state.steps.items()}
    report_metadata = (
        metadata.model_copy(update={"source_url": None})
        if metadata.source_type == "webpage_media"
        else metadata
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_status": state.project_status,
        "source": report_metadata.model_dump(mode="json"),
        "video_duration_seconds": metadata.duration,
        "subtitle_source": subtitle_source or metadata.subtitle_kind,
        "whisper_model": whisper_model,
        "translation_provider": translation_provider,
        "subtitle_cue_count": cue_count,
        "manually_flagged_cue_ids": flagged_cues or [],
        "render_parameters": render_parameters or {},
        "subtitle_quality": subtitle_quality or {},
        "output_paths": [str(path.resolve()) for path in (output_paths or []) if path.exists()],
        "processing_time_by_stage": stage_timings,
        "performance_summary": _performance_summary(state),
        "warnings": warnings or [],
        "errors": errors or [],
        "steps": {name: record.model_dump(mode="json") for name, record in state.steps.items()},
        "estimated_api_usage": {},
    }


def write_report(logs_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    json_path = logs_dir / "report.json"
    markdown_path = logs_dir / "report.md"
    atomic_write_json(json_path, report)
    lines = [
        "# Processing report",
        "",
        f"- Status: {report['project_status']}",
        f"- Source: {report['source']['title']}",
        f"- Duration: {report['video_duration_seconds']:.2f} seconds",
        f"- Subtitle source: {report['subtitle_source'] or 'not yet available'}",
        f"- Translation provider: {report['translation_provider'] or 'not yet selected'}",
        f"- Subtitle cues: {report['subtitle_cue_count']}",
        "",
        "## Outputs",
        "",
    ]
    lines.extend(f"- `{path}`" for path in report["output_paths"])
    lines += ["", "## Warnings", ""]
    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- None")
    lines += ["", "## Errors", ""]
    if report["errors"]:
        lines.extend(f"- {error}" for error in report["errors"])
    else:
        lines.append("- None")
    lines += ["", "## Subtitle quality check", ""]
    quality = report["subtitle_quality"]
    if quality:
        lines.extend(
            [
                f"- Target language: {quality.get('target_language', 'unknown')}",
                f"- Flagged cues: {quality.get('flagged_cue_count', 0)}",
                f"- Findings: {quality.get('finding_count', 0)}",
            ]
        )
        categories = quality.get("findings_by_category", {})
        if categories:
            lines.append(
                "- By category: "
                + ", ".join(f"{name}={count}" for name, count in categories.items())
            )
    else:
        lines.append("- Not available")
    lines += ["", "## Stage timings", ""]
    lines.extend(
        f"- {name}: {elapsed if elapsed is not None else 'n/a'} s"
        for name, elapsed in report["processing_time_by_stage"].items()
    )
    performance = report.get("performance_summary", {})
    if performance:
        lines += [
            "",
            "## Performance guidance",
            "",
            "- Slowest stage: "
            f"{performance.get('slowest_stage')} ({performance.get('slowest_stage_seconds')} s)",
            f"- Next step: {performance.get('recommendation', '')}",
        ]
    atomic_write_text(markdown_path, "\n".join(lines) + "\n")
    return json_path, markdown_path
