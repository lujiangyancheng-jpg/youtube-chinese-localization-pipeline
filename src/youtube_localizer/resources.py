from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def model_roots() -> list[Path]:
    """Return model roots for an installed offline bundle and a source checkout."""
    candidates: list[Path] = []
    if configured := os.getenv("YOUTUBE_LOCALIZER_MODELS"):
        candidates.append(Path(configured).expanduser())
    if home := os.getenv("YOUTUBE_LOCALIZER_HOME"):
        candidates.append(Path(home).expanduser() / "models")

    source_root = Path(__file__).resolve().parents[2]
    candidates.extend([source_root / "tools" / "models", source_root / "models"])
    executable = Path(sys.executable).resolve()
    candidates.extend(parent / "models" for parent in executable.parents[:4])

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_bundled_model(name: str) -> Path | None:
    for root in model_roots():
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def font_roots() -> list[Path]:
    """Return font roots for an installed bundle and a source checkout."""
    candidates: list[Path] = []
    if configured := os.getenv("YOUTUBE_LOCALIZER_FONTS"):
        candidates.append(Path(configured).expanduser())
    if home := os.getenv("YOUTUBE_LOCALIZER_HOME"):
        candidates.append(Path(home).expanduser() / "fonts")

    source_root = Path(__file__).resolve().parents[2]
    candidates.extend([source_root / "tools" / "fonts", source_root / "fonts"])
    executable = Path(sys.executable).resolve()
    candidates.extend(parent / "fonts" for parent in executable.parents[:4])

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def bundled_fonts_directory() -> Path | None:
    """Return a local font directory that libass can use without system installation."""
    for root in font_roots():
        if root.is_dir() and any(
            path.is_file() for suffix in ("*.ttf", "*.otf", "*.ttc") for path in root.glob(suffix)
        ):
            return root
    return None


def resolve_whisper_model(model: str) -> tuple[str, bool]:
    """Resolve a configured Whisper size to bundled weights when available."""
    configured = Path(model).expanduser()
    if configured.is_dir():
        return str(configured.resolve()), True
    if bundled := find_bundled_model(f"faster-whisper-{model}"):
        return str(bundled), True
    return model, False


def bundled_ollama_models() -> Path | None:
    for root in model_roots():
        candidate = root / "ollama"
        if (candidate / "blobs").is_dir() and (candidate / "manifests").is_dir():
            return candidate
    return None


def ollama_executable() -> Path | None:
    if configured := os.getenv("OLLAMA_PATH"):
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    if discovered := shutil.which("ollama"):
        return Path(discovered).resolve()
    if home := os.getenv("YOUTUBE_LOCALIZER_HOME"):
        candidate = Path(home) / "runtime" / "ollama" / "ollama.exe"
        if candidate.is_file():
            return candidate.resolve()
    for parent in Path(sys.executable).resolve().parents[:4]:
        candidate = parent / "runtime" / "ollama" / "ollama.exe"
        if candidate.is_file():
            return candidate.resolve()
    if local_app_data := os.getenv("LOCALAPPDATA"):
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return candidate.resolve()
    return None


def cuda_runtime_directories() -> list[Path]:
    """Find CUDA 12 DLL folders shipped with a local Ollama installation.

    CTranslate2 dynamically loads CUDA on Windows.  The offline bundle already
    includes the matching CUDA 12 redistributable with Ollama, but the DLLs live
    in Ollama's ``lib/ollama/cuda_v12`` folder rather than beside ``ollama.exe``.
    Returning this explicitly lets Whisper safely opt into the bundled runtime.
    """
    candidates: list[Path] = []
    if configured := os.getenv("YOUTUBE_LOCALIZER_CUDA_RUNTIME"):
        candidates.extend(Path(item).expanduser() for item in configured.split(os.pathsep) if item)
    if executable := ollama_executable():
        candidates.extend(
            [
                executable.parent / "lib" / "ollama" / "cuda_v12",
                executable.parent,
            ]
        )

    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (
            resolved.is_dir()
            and (resolved / "cublas64_12.dll").is_file()
            and resolved not in unique
        ):
            unique.append(resolved)
    return unique
