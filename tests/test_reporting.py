from __future__ import annotations

from youtube_localizer.reporting import load_report_context
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
