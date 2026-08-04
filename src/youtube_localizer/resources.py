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
