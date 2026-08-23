from __future__ import annotations

from youtube_localizer.models import PipelineStateData, SourceMetadata, StepRecord
from youtube_localizer.reporting import build_report, load_report_context, write_report
from youtube_localizer.utils.files import atomic_write_json


def test_load_report_context_keeps_existing_outputs_and_ignores_stale_paths(tmp_path) -> None:
    logs = tmp_path / "logs"
    kept = tmp_path / "kept.mp4"
    kept.write_bytes(b"video")
    atomic_write_json(
        logs / "report.json",
        {
            "warnings": ["one", "one", 2],
            "output_paths": [str(kept), str(tmp_path / "missing.mp4"), 42],
        },
    )

    warnings, outputs = load_report_context(logs)

    assert warnings == ["one", "2"]
    assert outputs == [kept]


def test_report_identifies_the_slowest_stage_and_gives_a_relevant_next_step(tmp_path) -> None:
    state = PipelineStateData(
        steps={
            "acquire": StepRecord(
                name="acquire",
                status="completed",
                started_at="2026-08-10T00:00:00Z",
                elapsed_seconds=27.0,
                input_hash="input",
                config_hash="config",
            ),
            "render": StepRecord(
                name="render",
                status="completed",
                started_at="2026-08-10T00:01:00Z",
                elapsed_seconds=179.0,
                input_hash="input",
                config_hash="config",
            ),
        }
    )
    metadata = SourceMetadata(
        source_type="local",
        source_input="source.mp4",
        video_id="report-test",
        title="Report test",
    )

    report = build_report(metadata, state)
    _, markdown = write_report(tmp_path, report)

    assert report["performance_summary"]["slowest_stage"] == "render"
    assert "NVENC" in report["performance_summary"]["recommendation"]
    assert "Slowest stage: render (179.0 s)" in markdown.read_text(encoding="utf-8")


def test_webpage_report_omits_the_resolved_media_signature() -> None:
    metadata = SourceMetadata(
        source_type="webpage_media",
        source_input="https://creator.example.com/watch/lesson.html",
        source_url="https://cdn.example.com/master.m3u8?token=secret",
        video_id="lesson",
        title="Lesson",
    )

    report = build_report(metadata, PipelineStateData())

    assert report["source"]["source_input"] == metadata.source_input
    assert report["source"]["source_url"] is None
