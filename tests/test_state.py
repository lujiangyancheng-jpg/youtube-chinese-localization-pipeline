from __future__ import annotations

import json

from youtube_localizer.models import StepRecord
from youtube_localizer.state import PipelineState, find_recoverable_projects, resume_decision


def test_resume_logic_requires_matching_hashes_and_outputs() -> None:
    record = StepRecord(
        name="render",
        status="completed",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        input_hash="input",
        config_hash="config",
    )
    assert resume_decision(record, input_hash="input", config_hash="config", outputs_exist=True)
    assert not resume_decision(
        record, input_hash="changed", config_hash="config", outputs_exist=True
    )
    assert not resume_decision(
        record, input_hash="input", config_hash="config", outputs_exist=False
    )


def test_pipeline_state_detects_changed_completed_output(tmp_path) -> None:
    state = PipelineState(tmp_path / "pipeline_state.json")
    output = tmp_path / "localized.srt"

    with state.step("translate", input_hash="input", config_hash="config") as outputs:
        output.write_text("first version", encoding="utf-8")
        outputs.append(output)

    assert state.can_skip(
        "translate", input_hash="input", config_hash="config", output_files=[output]
    )
    output.write_text("other version", encoding="utf-8")
    assert not state.can_skip(
        "translate", input_hash="input", config_hash="config", output_files=[output]
    )


def test_pipeline_state_upgrades_legacy_output_metadata(tmp_path) -> None:
    output = tmp_path / "source.mp4"
    output.write_bytes(b"media")
    state_file = tmp_path / "pipeline_state.json"
    state_file.write_text(
        json.dumps(
            {
                "version": 1,
                "project_status": "incomplete",
                "steps": {
                    "download": {
                        "name": "download",
                        "status": "completed",
                        "started_at": "2026-01-01T00:00:00Z",
                        "input_hash": "input",
                        "config_hash": "config",
                        "output_files": [str(output)],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    state = PipelineState(state_file)
    assert state.can_skip(
        "download", input_hash="input", config_hash="config", output_files=[output]
    )
    assert state.data.version == 2
    assert state.data.steps["download"].output_artifacts[0].size_bytes == 5


def test_find_recoverable_projects_ignores_complete_and_broken_state(tmp_path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    state = PipelineState(incomplete / "pipeline_state.json")
    output = incomplete / "source.mp4"
    with state.step("download", input_hash="input", config_hash="config") as outputs:
        output.write_bytes(b"media")
        outputs.append(output)

    complete = tmp_path / "complete"
    complete.mkdir()
    complete_state = PipelineState(complete / "pipeline_state.json")
    complete_state.data.steps = state.data.steps
    complete_state.mark_status("complete")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pipeline_state.json").write_text("not json", encoding="utf-8")

    candidates = find_recoverable_projects(tmp_path)

    assert [candidate.root for candidate in candidates] == [incomplete.resolve()]
