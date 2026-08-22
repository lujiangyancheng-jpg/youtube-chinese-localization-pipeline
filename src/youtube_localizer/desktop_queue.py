"""Versioned, non-secret desktop queue state for crash and restart recovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .onboarding import onboarding_state_directory
from .utils.files import atomic_write_json, load_json

QUEUE_SCHEMA_VERSION = 1
VALID_TASK_STATES = frozenset(
    {
        "pending",
        "analyzing",
        "ready",
        "queued",
        "running",
        "paused",
        "failed",
        "completed",
    }
)


@dataclass(frozen=True, slots=True)
class DesktopTaskSnapshot:
    source: str
    title: str = ""
    media_summary: str = ""
    state: str = "pending"
    progress: float = 0.0
    project_path: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class DesktopQueueSnapshot:
    schema_version: int = QUEUE_SCHEMA_VERSION
    updated_at: str = ""
    tasks: tuple[DesktopTaskSnapshot, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at or datetime.now(UTC).isoformat(),
            "tasks": [asdict(task) for task in self.tasks],
        }


def desktop_queue_path(environment: Mapping[str, str] | None = None) -> Path:
    return onboarding_state_directory(environment) / "desktop-queue.json"


def _task_from_mapping(data: Mapping[str, Any]) -> DesktopTaskSnapshot | None:
    source = data.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    state = data.get("state")
    if state not in VALID_TASK_STATES:
        state = "pending"
    # A process cannot still be running after a new desktop process starts.  Mark it as safely
    # resumable while the pipeline's own stage fingerprints decide what work must be repeated.
    if state in {"analyzing", "queued", "running"}:
        state = "paused"
    progress = data.get("progress")
    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        progress = 0.0
    progress = min(100.0, max(0.0, float(progress)))

    def text_value(name: str) -> str:
        value = data.get(name)
        return value.strip() if isinstance(value, str) else ""

    return DesktopTaskSnapshot(
        source=source.strip(),
        title=text_value("title"),
        media_summary=text_value("media_summary"),
        state=state,
        progress=progress,
        project_path=text_value("project_path"),
        error=text_value("error"),
    )


def load_desktop_queue(
    *, environment: Mapping[str, str] | None = None, queue_path: Path | None = None
) -> DesktopQueueSnapshot:
    path = queue_path or desktop_queue_path(environment)
    try:
        data = load_json(path)
    except (OSError, TypeError, ValueError):
        return DesktopQueueSnapshot()
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return DesktopQueueSnapshot()
    if data.get("schema_version", QUEUE_SCHEMA_VERSION) != QUEUE_SCHEMA_VERSION:
        return DesktopQueueSnapshot()
    tasks = tuple(
        task
        for item in data["tasks"]
        if isinstance(item, dict) and (task := _task_from_mapping(item)) is not None
    )
    updated_at = data.get("updated_at")
    return DesktopQueueSnapshot(
        updated_at=updated_at if isinstance(updated_at, str) else "",
        tasks=tasks,
    )


def save_desktop_queue(
    snapshot: DesktopQueueSnapshot,
    *,
    environment: Mapping[str, str] | None = None,
    queue_path: Path | None = None,
) -> Path:
    path = queue_path or desktop_queue_path(environment)
    atomic_write_json(path, snapshot.to_dict())
    return path


def clear_desktop_queue(
    *, environment: Mapping[str, str] | None = None, queue_path: Path | None = None
) -> None:
    path = queue_path or desktop_queue_path(environment)
    path.unlink(missing_ok=True)
