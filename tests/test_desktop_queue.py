from __future__ import annotations

import json

from youtube_localizer.desktop_queue import (
    DesktopQueueSnapshot,
    DesktopTaskSnapshot,
    clear_desktop_queue,
    load_desktop_queue,
    save_desktop_queue,
)


def test_queue_round_trip_contains_no_credentials(tmp_path) -> None:
    path = tmp_path / "desktop-queue.json"
    snapshot = DesktopQueueSnapshot(
        tasks=(
            DesktopTaskSnapshot(
                source="https://youtu.be/example",
                title="Example",
                media_summary="1:00 · 1080p",
                state="failed",
                progress=42.0,
                project_path="D:/Localized/Example",
                error="network unavailable",
            ),
        )
    )

    save_desktop_queue(snapshot, queue_path=path)

    assert load_desktop_queue(queue_path=path).tasks == snapshot.tasks
    serialized = json.loads(path.read_text(encoding="utf-8"))
    assert "api_key" not in serialized
    assert serialized["updated_at"]


def test_running_tasks_become_resumable_after_restart(tmp_path) -> None:
    path = tmp_path / "desktop-queue.json"
    path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"source": "one", "state": "running", "progress": 27},
                    {"source": "two", "state": "queued", "progress": 0},
                    {"source": "three", "state": "completed", "progress": 100},
                ]
            }
        ),
        encoding="utf-8",
    )

    tasks = load_desktop_queue(queue_path=path).tasks

    assert [task.state for task in tasks] == ["paused", "paused", "completed"]
    assert tasks[0].progress == 27


def test_invalid_queue_entries_are_ignored_or_normalized(tmp_path) -> None:
    path = tmp_path / "desktop-queue.json"
    path.write_text(
        json.dumps(
            {
                "tasks": [
                    None,
                    {"source": ""},
                    {"source": " valid ", "state": "mystery", "progress": 999},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_desktop_queue(queue_path=path).tasks == (
        DesktopTaskSnapshot(source="valid", state="pending", progress=100.0),
    )


def test_corrupt_queue_is_empty_and_clear_is_idempotent(tmp_path) -> None:
    path = tmp_path / "desktop-queue.json"
    path.write_text("{broken", encoding="utf-8")

    assert not load_desktop_queue(queue_path=path).tasks
    clear_desktop_queue(queue_path=path)
    clear_desktop_queue(queue_path=path)
    assert not path.exists()


def test_newer_queue_schema_is_ignored_safely(tmp_path) -> None:
    path = tmp_path / "desktop-queue.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "tasks": [{"source": "one", "state": "running"}],
            }
        ),
        encoding="utf-8",
    )

    assert not load_desktop_queue(queue_path=path).tasks
