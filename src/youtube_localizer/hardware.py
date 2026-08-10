from __future__ import annotations

import csv
from dataclasses import dataclass

from .errors import ExternalToolError
from .utils.subprocesses import resolve_executable, run_command


@dataclass(frozen=True)
class NvidiaGPU:
    name: str
    driver_version: str
    total_memory_mib: int | None
    used_memory_mib: int | None


def query_nvidia_gpus() -> list[NvidiaGPU]:
    """Read lightweight NVIDIA inventory data when nvidia-smi is available."""
    executable = resolve_executable("nvidia-smi")
    if executable is None:
        return []
    try:
        result = run_command(
            [
                executable,
                "--query-gpu=name,driver_version,memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
        )
    except ExternalToolError:
        return []

    gpus: list[NvidiaGPU] = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 4:
            continue
        name, driver, total, used = (item.strip() for item in row)
        if not name:
            continue
        gpus.append(
            NvidiaGPU(
                name=name,
                driver_version=driver,
                total_memory_mib=_parse_memory_mib(total),
                used_memory_mib=_parse_memory_mib(used),
            )
        )
    return gpus


def probe_h264_nvenc(ffmpeg: str | None = None) -> tuple[bool, str]:
    """Verify that FFmpeg can initialize the NVIDIA encoder on this exact driver."""
    executable = ffmpeg or resolve_executable("ffmpeg")
    if executable is None:
        return False, "FFmpeg was not found."
    try:
        run_command(
            [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:r=1",
                "-frames:v",
                "1",
                "-an",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            timeout=10,
        )
    except ExternalToolError as exc:
        detail = str(exc)
        normalized = detail.casefold()
        if "minimum required nvidia driver" in normalized or "nvenc api version" in normalized:
            return (
                False,
                "当前 NVIDIA 驱动版本不足以供此 FFmpeg 使用 NVENC；更新驱动后可启用显卡压制。",
            )
        if "no nvenc capable devices" in normalized:
            return False, "FFmpeg 没有发现可用的 NVIDIA NVENC 编码器。"
        return False, f"NVENC 测试失败：{_last_detail_line(detail)}"
    return True, "NVENC 硬件编码可用。"


def format_nvidia_gpus(gpus: list[NvidiaGPU]) -> str:
    if not gpus:
        return "未检测到可读取的 NVIDIA GPU 信息。"
    entries = []
    for gpu in gpus:
        memory = (
            f"，显存 {gpu.used_memory_mib}/{gpu.total_memory_mib} MiB"
            if gpu.total_memory_mib is not None and gpu.used_memory_mib is not None
            else ""
        )
        driver = f"，驱动 {gpu.driver_version}" if gpu.driver_version else ""
        entries.append(f"{gpu.name}{driver}{memory}")
    return "；".join(entries)


def _parse_memory_mib(value: str) -> int | None:
    try:
        return int(float(value))
    except ValueError:
        return None


def _last_detail_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1] if lines else "未知错误"
