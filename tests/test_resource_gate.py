from __future__ import annotations

from youtube_localizer.hardware import NvidiaGPU, SystemResources
from youtube_localizer.resource_gate import (
    ResourceSchedule,
    choose_resource_schedule,
    heavy_workload_lock_path,
)


def test_high_headroom_nvidia_system_uses_separate_compute_and_encoder_lanes(
    tmp_path, monkeypatch
) -> None:
    schedule = choose_resource_schedule(
        SystemResources(logical_cpu_count=16, memory_mib=32 * 1024),
        [NvidiaGPU("RTX 5070", "stable", 12 * 1024, 1024)],
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert schedule.mode == "split"
    assert heavy_workload_lock_path("compute", schedule=schedule).name == "compute.lock"
    assert heavy_workload_lock_path("encoder", schedule=schedule).name == "encoder.lock"


def test_lower_memory_system_keeps_all_heavy_work_serialized(tmp_path, monkeypatch) -> None:
    schedule = choose_resource_schedule(
        SystemResources(logical_cpu_count=8, memory_mib=16 * 1024),
        [NvidiaGPU("RTX", "stable", 12 * 1024, 1024)],
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert schedule.mode == "serialized"
    assert heavy_workload_lock_path("compute", schedule=schedule) == heavy_workload_lock_path(
        "encoder", schedule=schedule
    )


def test_gpu_memory_threshold_prevents_unsafe_overlap() -> None:
    schedule = choose_resource_schedule(
        SystemResources(logical_cpu_count=16, memory_mib=32 * 1024),
        [NvidiaGPU("RTX", "stable", 8 * 1024, 1024)],
    )

    assert schedule == ResourceSchedule("serialized", "safe mode: less than 10 GiB GPU memory")
