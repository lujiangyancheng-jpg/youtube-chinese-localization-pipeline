from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from ..errors import ExternalToolError

LOGGER = logging.getLogger(__name__)
WINDOWS_CONTROL_C_EXIT = 0xC000013A


def hidden_console_kwargs() -> dict[str, int]:
    """Prevent console windows from appearing for helper tools started by the desktop app."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


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
            **hidden_console_kwargs(),
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
        _raise_command_error(command, result.returncode, detail)
    return result


def _raise_command_error(command: list[str], returncode: int, detail: str = "") -> None:
    unsigned_returncode = returncode & 0xFFFFFFFF
    if unsigned_returncode == WINDOWS_CONTROL_C_EXIT:
        message = (
            f"{command[0]} was interrupted by a stop or window-close signal "
            "(Windows status 0xC000013A). Keep the localizer window open while "
            "rendering; resume the project to retry only the unfinished stage."
        )
    else:
        message = f"{command[0]} failed with exit code {returncode}."
    raise ExternalToolError(
        message + (f"\n{detail}" if detail else ""),
        command=command,
    )


def run_streaming_command(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command while consuming merged output without hiding long-task progress."""
    command = [str(arg) for arg in args]
    if resolved := resolve_executable(command[0]):
        command[0] = resolved
    LOGGER.debug("Running streaming external command", extra={"command": command})
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **hidden_console_kwargs(),
        )
    except FileNotFoundError as exc:
        raise ExternalToolError(
            f"Required executable was not found: {command[0]}. "
            "Install it and ensure it is available on PATH.",
            command=command,
        ) from exc

    output_tail: deque[str] = deque(maxlen=100)
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.rstrip("\r\n")
        output_tail.append(line)
        if line_callback is not None:
            line_callback(line)
    returncode = process.wait()
    output = "\n".join(output_tail).strip()
    if returncode != 0:
        _raise_command_error(command, returncode, output[-4000:])
    return subprocess.CompletedProcess(command, returncode, stdout=output, stderr="")
