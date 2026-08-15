from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from pydantic import ValidationError

from .models import OutputArtifact, PipelineStateData, StepRecord
from .utils.files import atomic_write_json, load_json
from .utils.hashing import hash_file

_FULL_HASH_LIMIT = 8 * 1024 * 1024
_SAMPLE_SIZE = 1024 * 1024


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RecoverableProject:
    root: Path
    updated_at: str
    failed_steps: tuple[str, ...]


def _sampled_file_hash(path: Path, size: int) -> str:
    """Fingerprint a large file without rereading the entire video during every resume."""
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    positions = (0, max(0, size // 2 - _SAMPLE_SIZE // 2), max(0, size - _SAMPLE_SIZE))
    with path.open("rb") as handle:
        for position in dict.fromkeys(positions):
            handle.seek(position)
            digest.update(position.to_bytes(8, "little", signed=False))
            digest.update(handle.read(_SAMPLE_SIZE))
    return digest.hexdigest()


def build_output_artifact(path: Path) -> OutputArtifact:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Completed step output is missing or is not a file: {resolved}")
    size = resolved.stat().st_size
    if size <= 0:
        raise OSError(f"Completed step output is empty: {resolved}")
    if size <= _FULL_HASH_LIMIT:
        fingerprint = hash_file(resolved)
        kind = "sha256"
    else:
        fingerprint = _sampled_file_hash(resolved, size)
        kind = "sampled-sha256-v1"
    return OutputArtifact(
        path=str(resolved),
        size_bytes=size,
        fingerprint=fingerprint,
        fingerprint_kind=kind,
    )


def output_artifact_is_current(artifact: OutputArtifact, path: Path) -> bool:
    try:
        current = build_output_artifact(path)
    except OSError:
        return False
    return bool(
        Path(artifact.path).expanduser().resolve() == path.expanduser().resolve()
        and artifact.size_bytes == current.size_bytes
        and artifact.fingerprint_kind == current.fingerprint_kind
        and artifact.fingerprint == current.fingerprint
    )


def find_recoverable_projects(output_root: Path) -> list[RecoverableProject]:
    """Return valid, incomplete project workspaces directly below an output directory."""
    root = output_root.expanduser()
    if not root.is_dir():
        return []
    recoverable: list[RecoverableProject] = []
    try:
        candidates = list(root.iterdir())
    except OSError:
        return []
    for candidate in candidates:
        state_file = candidate / "pipeline_state.json"
        if not state_file.is_file():
            continue
        try:
            data = PipelineStateData.model_validate(load_json(state_file))
        except (OSError, ValueError, ValidationError):
            continue
        if data.project_status == "complete" or not data.steps:
            continue
        failed = tuple(sorted(name for name, step in data.steps.items() if step.status == "failed"))
        recoverable.append(RecoverableProject(candidate.resolve(), data.updated_at, failed))
    return sorted(recoverable, key=lambda item: item.updated_at, reverse=True)


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
        if not resume_decision(
            record,
            input_hash=input_hash,
            config_hash=config_hash,
            outputs_exist=all(path.is_file() and path.stat().st_size > 0 for path in output_files),
        ):
            return False
        assert record is not None
        expected = [path.expanduser().resolve() for path in output_files]
        recorded = [Path(path).expanduser().resolve() for path in record.output_files]
        if recorded and recorded != expected:
            return False
        if record.output_artifacts:
            if len(record.output_artifacts) != len(expected):
                return False
            return all(
                output_artifact_is_current(artifact, path)
                for artifact, path in zip(record.output_artifacts, expected, strict=True)
            )

        # Version-1 projects did not have fingerprints. Preserve their resumability, but only
        # after establishing an integrity baseline that all future resumes must match.
        try:
            record.output_files = [str(path) for path in expected]
            record.output_artifacts = [build_output_artifact(path) for path in expected]
        except OSError:
            return False
        self.data.version = 2
        self.save()
        return True

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
            try:
                record.output_files = [str(path.resolve()) for path in outputs]
                record.output_artifacts = [build_output_artifact(path) for path in outputs]
            except OSError as exc:
                record.status = "failed"
                record.ended_at = utc_now()
                record.error_message = str(exc)
                record.elapsed_seconds = round(monotonic() - started, 3)
                self.save()
                raise
            else:
                record.status = "completed"
                record.ended_at = utc_now()
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
