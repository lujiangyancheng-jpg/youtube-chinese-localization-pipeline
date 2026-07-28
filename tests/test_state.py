from __future__ import annotations

from youtube_localizer.models import StepRecord
from youtube_localizer.state import resume_decision


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
