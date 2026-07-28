from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from .models import PipelineStateData, StepRecord
from .utils.files import atomic_write_json, load_json


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class PipelineState:
    def __init__(self, path: Path, *, source_input: str = "") -> None:
        self.path = path
        if path.is_file():
            self.data = PipelineStateData.model_validate(load_json(path))
        else:
            self.data = PipelineStateData(source_input=source_input, updated_at=utc_now())
            self.save()

    def save(self) -> None:
        self.data.updated_at = utc_now()
        atomic_write_json(self.path, self.data.model_dump(mode="json"))

    def can_skip(
        self,
        name: str,
        *,
        input_hash: str,
        config_hash: str,
        output_files: list[Path],
        force: bool = False,
    ) -> bool:
        if force:
            return False
        record = self.data.steps.get(name)
        return bool(
            record
            and record.status == "completed"
            and record.input_hash == input_hash
            and record.config_hash == config_hash
            and all(path.exists() for path in output_files)
        )

    @contextmanager
    def step(
        self,
        name: str,
        *,
        input_hash: str,
        config_hash: str,
    ) -> Iterator[list[Path]]:
        started = monotonic()
        previous = self.data.steps.get(name)
        retry_count = (previous.retry_count + 1) if previous else 0
        record = StepRecord(
            name=name,
            status="running",
            started_at=utc_now(),
            input_hash=input_hash,
            config_hash=config_hash,
            retry_count=retry_count,
        )
        self.data.steps[name] = record
        self.data.project_status = "incomplete"
        self.save()
        outputs: list[Path] = []
        try:
            yield outputs
        except BaseException as exc:
            record.status = "failed"
            record.ended_at = utc_now()
            record.error_message = str(exc)
            record.elapsed_seconds = round(monotonic() - started, 3)
            self.save()
            raise
        else:
            record.status = "completed"
            record.ended_at = utc_now()
            record.output_files = [str(path.resolve()) for path in outputs]
            record.error_message = None
            record.elapsed_seconds = round(monotonic() - started, 3)
            self.save()

    def mark_status(self, status: str) -> None:
        self.data.project_status = status
        self.save()


def resume_decision(
    record: StepRecord | None,
    *,
    input_hash: str,
    config_hash: str,
    outputs_exist: bool,
) -> bool:
    """Pure helper used by tests and PipelineState.can_skip."""
    return bool(
        record
        and record.status == "completed"
        and record.input_hash == input_hash
        and record.config_hash == config_hash
        and outputs_exist
    )
