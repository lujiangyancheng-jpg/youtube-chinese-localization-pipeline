from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ..errors import ExternalToolError

LOGGER = logging.getLogger(__name__)


def resolve_executable(name: str) -> str | None:
    candidate = Path(name)
    if candidate.parent != Path(".") and candidate.is_file():
        return str(candidate.resolve())
    discovered = shutil.which(name)
    if discovered:
        return discovered
    stem = Path(name).stem.upper().replace("-", "_")
    env_path = os.getenv(f"{stem}_PATH")
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())
    executable = f"{name}.exe" if os.name == "nt" and not name.endswith(".exe") else name
    project_root = Path(__file__).resolve().parents[3]
    search_directories = [
        Path.cwd() / "tools" / "ffmpeg" / "bin",
        project_root / "tools" / "ffmpeg" / "bin",
        Path.cwd() / "ffmpeg" / "bin",
    ]
    installed_binaries: list[Path] = []
    if os.name == "nt" and (local_app_data := os.getenv("LOCALAPPDATA")):
        local_root = Path(local_app_data)
        search_directories.append(local_root / "Microsoft" / "WinGet" / "Links")
        winget_packages = local_root / "Microsoft" / "WinGet" / "Packages"
        installed_binaries = list(
            winget_packages.glob(f"Gyan.FFmpeg_*/*/bin/{executable}"),
        )
    for directory in search_directories:
        local = directory / executable
        if local.is_file():
            return str(local.resolve())
    if installed_binaries:
        newest = max(installed_binaries, key=lambda path: path.stat().st_mtime_ns)
        return str(newest.resolve())
    return None


def run_command(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [str(arg) for arg in args]
    if resolved := resolve_executable(command[0]):
        command[0] = resolved
    LOGGER.debug("Running external command", extra={"command": command})
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=capture_output,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ExternalToolError(
            f"Required executable was not found: {command[0]}. "
            "Install it and ensure it is available on PATH.",
            command=command,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            f"Command timed out after {timeout} seconds: {command[0]}", command=command
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-4000:]
        raise ExternalToolError(
            f"{command[0]} failed with exit code {result.returncode}."
            + (f"\n{detail}" if detail else ""),
            command=command,
        )
    return result
